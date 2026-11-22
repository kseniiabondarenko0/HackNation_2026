"""Regressions from the whole-project audit; network/AI responses are controlled test data."""
from datetime import date, datetime, timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from analysis import ai, demo, llmbase, service
from analysis.models import Analysis, LLMUsage
from collection.models import Article
from collection.extract import content_hash
from collection.window import is_old
from collection.services import _fetch_article
from tests.test_ai import GEM, GRQ_OFF, Net, QUOTE, TEXT, err, g_reply, mk_article, raw


@override_settings(GEMINI=GEM, GROQ=GRQ_OFF)
class ActualRequestBudgetTests(TestCase):
    def test_explicit_zero_budget_does_not_use_the_default_limit(self):
        mk_article()
        with mock.patch('analysis.llmbase.httpx.post') as post:
            self.assertEqual(service.analyze_pending('ai',max_calls=0), 0)
        post.assert_not_called()

    def test_each_http_retry_is_counted(self):
        net = Net([err(503), g_reply(raw())])
        with mock.patch('analysis.llmbase.httpx.post', side_effect=net):
            ai.analyze(mk_article())
        row = LLMUsage.objects.get(provider='gemini')
        self.assertEqual((row.calls, row.errors, row.tokens_in, row.tokens_out), (2, 1, 100, 50))

    def test_retry_stops_at_the_daily_limit(self):
        LLMUsage.objects.create(provider='gemini', day=date.today(), calls=GEM['MAX_CALLS_PER_DAY'] - 1)
        net = Net([err(503), g_reply(raw())])
        with mock.patch('analysis.llmbase.httpx.post', side_effect=net), self.assertRaises(llmbase.LLMError) as raised:
            ai.analyze(mk_article())
        self.assertEqual(raised.exception.kind, 'budget')
        self.assertEqual(net.count(), 1)
        self.assertEqual(LLMUsage.objects.get(provider='gemini').calls, GEM['MAX_CALLS_PER_DAY'])

    def test_the_last_call_is_reserved_before_http_starts(self):
        article = mk_article()
        LLMUsage.objects.create(provider='gemini', day=date.today(), calls=GEM['MAX_CALLS_PER_DAY'] - 1)
        nested_kinds = []
        def outer_request(*args, **kwargs):
            if post.call_count > 1:
                self.fail('A second HTTP request spent the same last budget slot')
            with self.assertRaises(llmbase.LLMError) as raised:
                # Simulate another worker entering while the first HTTP request is in flight.
                ai.analyze(article)
            nested_kinds.append(raised.exception.kind)
            return g_reply(raw())
        with mock.patch('analysis.llmbase.httpx.post', side_effect=outer_request) as post:
            ai.analyze(article)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(nested_kinds, ['budget'])

    def test_all_failed_attempts_are_counted(self):
        net = Net([err(503)] * 3)
        with mock.patch('analysis.llmbase.httpx.post', side_effect=net), self.assertRaises(llmbase.LLMError):
            ai.analyze(mk_article())
        row = LLMUsage.objects.get(provider='gemini')
        self.assertEqual((row.calls, row.errors), (3, 3))


class MetadataRefreshTests(TestCase):
    def setUp(self):
        self.article = mk_article(text=TEXT * 3, published_at=timezone.now() - timedelta(days=5))
        self.article.content_hash = content_hash(self.article.text)
        self.article.save(update_fields=['content_hash'])
        self.analysis = Analysis.objects.create(article=self.article, backend='ai',
            input_key=service._key(self.article, 'ai'), verdict='glowna', potential=72,
            data=ai.finalize_ai(raw(), self.article), handling='kontakt')

    def fetch(self, **metadata):
        data = {'title': self.article.title, 'text': self.article.text, 'published_at': self.article.published_at, **metadata}
        stats = dict.fromkeys(('fetched','updated','duplicates','skipped','errors','unchanged'),0)
        with mock.patch('collection.services.extract_article', return_value=data):
            _fetch_article(self.article, lambda url: ('https://u.example.pl/current-url', '<html>test</html>'), stats)
        self.article.refresh_from_db()
        self.analysis.refresh_from_db()
        return stats

    def test_identical_body_keeps_current_title_date_and_final_url(self):
        new_date = timezone.now()
        self.fetch(title='Poprawiony tytuł', published_at=new_date)
        self.assertEqual(self.article.title, 'Poprawiony tytuł')
        self.assertEqual(self.article.published_at, new_date)
        self.assertEqual(self.article.final_url, 'https://u.example.pl/current-url')

    def test_metadata_change_queues_reanalysis_without_global_cache_invalidation(self):
        self.fetch(title='Nowy tytuł z aktualnymi warunkami')
        self.assertTrue(self.analysis.data.get('stale'))
        self.assertNotEqual(self.analysis.input_key, service._key(self.article, 'ai'))
        self.assertIsNone(self.analysis.potential)
        self.assertEqual(self.analysis.handling, 'kontakt')
        self.assertEqual(self.analysis.data['_previous']['text'], TEXT * 3)

    def test_missing_extracted_date_does_not_erase_a_known_date(self):
        before = self.article.published_at
        self.fetch(published_at=None)
        self.assertEqual(self.article.published_at, before)

    def test_unchanged_metadata_keeps_the_current_analysis(self):
        self.article.final_url = 'https://u.example.pl/current-url'
        self.article.save(update_fields=['final_url'])
        stats = self.fetch()
        self.assertEqual(stats['unchanged'], 1)
        self.assertFalse(self.analysis.data.get('stale'))
        self.assertEqual(self.analysis.potential, 72)

    @override_settings(GEMINI=GEM, GROQ=GRQ_OFF)
    def test_metadata_only_change_is_reanalysed_once(self):
        self.fetch(title='Poprawiony tytuł publikacji')
        net = Net([g_reply(raw())])
        with mock.patch('analysis.llmbase.httpx.post', side_effect=net):
            self.assertEqual(service.analyze_pending('ai',max_calls=1), 1)
            self.assertEqual(service.analyze_pending('ai',max_calls=1), 0)
        self.analysis.refresh_from_db()
        self.assertFalse(self.analysis.data.get('stale'))
        self.assertEqual(net.count(), 1)


class SubmissionRefreshTests(TestCase):
    def test_empty_extraction_has_a_visible_error(self):
        with (mock.patch('web.views.safe_get', return_value=('https://example.org/empty', 'empty')),
                mock.patch('web.views.extract_article', return_value=None)):
            response = self.client.post(reverse('submit'), {'url':'https://example.org/empty'})
        self.assertContains(response, 'Na stronie nie znaleziono wystarczająco dużo tekstu')
        self.assertFalse(Article.objects.exists())

    def test_url_submission_preserves_the_publication_date_from_metadata(self):
        published = timezone.now() - timedelta(days=2)
        extracted = {'title':'Innowacja', 'text':TEXT * 3, 'published_at':published}
        with (mock.patch('web.views.safe_get', return_value=('https://example.org/article', 'html')),
                mock.patch('web.views.extract_article', return_value=extracted),
                mock.patch('web.views.analyze_article', side_effect=llmbase.LLMError('budget'))):
            response = self.client.post(reverse('submit'), {'url':'https://example.org/article'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Article.objects.get().published_at, published)


class CurrentExportTests(TestCase):
    def test_current_gemini_key_prefix_is_detected_without_disclosing_it(self):
        fake_key = 'AQ.' + 'synthetic_example_' * 3
        problems = demo.check_clean({'note':fake_key})
        self.assertTrue(problems)
        self.assertNotIn(fake_key, str(problems))

    def test_personal_data_is_not_echoed_in_export_diagnostics(self):
        private = 'example.user@example.org'
        problems = demo.check_clean({'note':private})
        self.assertTrue(problems)
        self.assertNotIn(private, str(problems))

    def test_groq_analysis_is_not_labelled_as_gemini(self):
        data = ai.finalize_ai(raw(), mk_article())
        self.assertNotIn('Gemini', data['caveat'])
        self.assertNotIn('Gemini', str(data['path']['reasons']))

    def test_legacy_cached_groq_card_does_not_repeat_a_gemini_label(self):
        article = mk_article()
        data = ai.finalize_ai(raw(), article)
        data['ai'].update(provider='groq', model='openai/gpt-oss-120b')
        data['caveat'] = 'Ocena wygenerowana przez model Gemini'
        data['path']['reasons'] = ['Ocena 72/100 (Gemini)']
        Analysis.objects.create(article=article, backend='ai', input_key='legacy', verdict='glowna', data=data)
        response = self.client.get(reverse('detail',args=[article.pk]))
        self.assertContains(response, 'groq / openai/gpt-oss-120b')
        self.assertNotContains(response, 'model Gemini')
        self.assertNotContains(response, '(Gemini)')

    @override_settings(ANALYSIS={**settings.ANALYSIS, 'WINDOW_MONTHS':0})
    def test_disabled_age_window_does_not_prune_records(self):
        old = mk_article(published_at=timezone.make_aware(datetime(1899,1,1)))
        out = StringIO()
        with mock.patch('collection.archive.append') as archive:
            call_command('prune_window', '--apply', stdout=out)
        self.assertTrue(Article.objects.filter(pk=old.pk).exists())
        archive.assert_not_called()
        self.assertIn('wyłączone', out.getvalue())

    @override_settings(ANALYSIS={**settings.ANALYSIS, 'WINDOW_MONTHS':0}, GEMINI=GEM, GROQ=GRQ_OFF)
    def test_disabled_window_has_no_hidden_1900_cutoff(self):
        article = mk_article(published_at=timezone.make_aware(datetime(1899,1,1)))
        self.assertFalse(is_old(article.published_at))
        from analysis import retention
        with mock.patch('collection.archive.append') as archive:
            retention._window(mock.Mock())
        archive.assert_not_called()
        with mock.patch('analysis.llmbase.httpx.post', side_effect=Net([g_reply(raw())])):
            self.assertEqual(service.analyze_pending('ai'), 1)
