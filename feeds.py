import datetime

from django.contrib.syndication.views import Feed
from django.core.cache import cache
from django.db.models import Q
from django.db.models.signals import post_save
from django.utils.hashcompat import md5_constructor
from django.views.decorators.http import condition

from main.models import Arch, Repo, Package
from news.models import News

CACHE_TIMEOUT = 1800
CACHE_PACKAGE_KEY = 'cache_package_latest'
CACHE_NEWS_KEY = 'cache_news_latest'

def retrieve_package_latest():
    # we could break this down based on the request url, but it would probably
    # cost us more in query time to do so.
    latest = cache.get(CACHE_PACKAGE_KEY)
    if latest:
        return latest
    try:
        latest = Package.objects.values('last_update').latest(
                'last_update')['last_update']
        cache.set(CACHE_PACKAGE_KEY, latest, CACHE_TIMEOUT)
        return latest
    except Package.DoesNotExist:
        pass
    return None

def refresh_package_latest(**kwargs):
    # We could delete the value, but that could open a race condition
    # where the new data wouldn't have been committed yet by the calling
    # thread. Update it instead.
    latest = Package.objects.values('last_update').latest(
            'last_update')['last_update']
    cache.set(CACHE_PACKAGE_KEY, latest, CACHE_TIMEOUT)

def package_etag(request, *args, **kwargs):
    latest = retrieve_package_latest()
    if latest:
        return md5_constructor(str(kwargs) + str(latest)).hexdigest()
    return None

def package_last_modified(request, *args, **kwargs):
    return retrieve_package_latest()

class PackageFeed(Feed):
    link = '/packages/'
    title_template = 'feeds/packages_title.html'
    description_template = 'feeds/packages_description.html'

    def __call__(self, request, *args, **kwargs):
        wrapper = condition(etag_func=package_etag, last_modified_func=package_last_modified)
        return wrapper(super(PackageFeed, self).__call__)(request, *args, **kwargs)

    def get_object(self, request, arch='', repo=''):
        obj = dict()
        qs = Package.objects.select_related('arch', 'repo').order_by('-last_update')

        if arch != '':
            # feed for a single arch, also include 'any' packages everywhere
            a = Arch.objects.get(name=arch)
            qs = qs.filter(Q(arch=a) | Q(arch__agnostic=True))
            obj['arch'] = a
        if repo != '':
            # feed for a single arch AND repo
            r = Repo.objects.get(name=repo)
            qs = qs.filter(repo=r)
            obj['repo'] = r
        obj['qs'] = qs[:50]
        return obj

    def title(self, obj):
        s = 'Arch Linux: Recent package updates'
        if 'repo' in obj:
            s += ' (%s [%s])' % (obj['arch'].name, obj['repo'].name.lower())
        elif 'arch' in obj:
            s += ' (%s)' % (obj['arch'].name)
        return s

    def description(self, obj):
        s = 'Recently updated packages in the Arch Linux package repositories'
        if 'arch' in obj:
            s += ' for the \'%s\' architecture' % obj['arch'].name.lower()
            if not obj['arch'].agnostic:
                s += ' (including \'any\' packages)'
        if 'repo' in obj:
            s += ' in the [%s] repository' % obj['repo'].name.lower()
        s += '.'
        return s

    def items(self, obj):
        return obj['qs']

    def item_pubdate(self, item):
        return item.last_update

    def item_categories(self, item):
        return (item.repo.name, item.arch.name)


def retrieve_news_latest():
    latest = cache.get(CACHE_NEWS_KEY)
    if latest:
        return latest
    try:
        latest = News.objects.values('last_modified').latest(
                'last_modified')['last_modified']
        cache.set(CACHE_NEWS_KEY, latest, CACHE_TIMEOUT)
        return latest
    except News.DoesNotExist:
        pass
    return None

def refresh_news_latest(**kwargs):
    # We could delete the value, but that could open a race condition
    # where the new data wouldn't have been committed yet by the calling
    # thread. Update it instead.
    latest = News.objects.values('last_modified').latest(
            'last_modified')['last_modified']
    cache.set(CACHE_NEWS_KEY, latest, CACHE_TIMEOUT)

def news_etag(request, *args, **kwargs):
    latest = retrieve_news_latest()
    if latest:
        return md5_constructor(str(latest)).hexdigest()
    return None

def news_last_modified(request, *args, **kwargs):
    return retrieve_news_latest()

class NewsFeed(Feed):
    title = 'Arch Linux: Recent news updates'
    link = '/news/'
    description = 'The latest and greatest news from the Arch Linux distribution.'
    title_template = 'feeds/news_title.html'
    description_template = 'feeds/news_description.html'

    def __call__(self, request, *args, **kwargs):
        wrapper = condition(etag_func=news_etag, last_modified_func=news_last_modified)
        return wrapper(super(NewsFeed, self).__call__)(request, *args, **kwargs)

    def items(self):
        return News.objects.select_related('author').order_by('-postdate', '-id')[:10]

    def item_pubdate(self, item):
        d = item.postdate
        return datetime.datetime(d.year, d.month, d.day)

    def item_author_name(self, item):
        return item.author.get_full_name()

# connect signals needed to keep cache in line with reality
post_save.connect(refresh_package_latest, sender=Package)
post_save.connect(refresh_news_latest, sender=News)

# vim: set ts=4 sw=4 et:
