import requests
import logging
import hashlib

from django.conf import settings
from django.http import HttpResponseBadRequest
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from mitxmako.shortcuts import render_to_string, render_to_response
from django_future.csrf import ensure_csrf_cookie
import enchant

from courseware.courses import get_course_with_access
from models import SearchResults
from es_requests import MongoIndexer


CONTENT_TYPES = ("transcript", "problem", "pdf")
log = logging.getLogger("mitx.courseware")


@ensure_csrf_cookie
def search(request, course_id):
    course = get_course_with_access(request.user, course_id, 'load')
    context = find(request, course_id)
    context.update({"course": course})
    return render_to_response("search_templates/search.html", context)


@ensure_csrf_cookie
def index_course(request):
    indexer = MongoIndexer()
    if "type_id" in request.POST.keys():
        indexer.index_course(request.POST["type_id"])
        return render_to_response(status=204)
    else:
        return HttpResponseBadRequest()


def find(request, course_id):
    database = settings.ES_DATABASE
    get_content = lambda request, content: content+"-index" if request.GET.get(content, False) else None
    query = request.GET.get("s", "*.*")
    page = request.GET.get("page", 1)
    results_per_page = request.GET.get("results", 15)
    index = ",".join(filter(None, [get_content(request, content) for content in CONTENT_TYPES]))
    if len(index) == 0:
        index = ",".join([content+"-index" for content in CONTENT_TYPES])
    if request.GET.get("all_courses" == "true", False):
        base_url = "/".join([database, index])
    else:
        course_hash = hashlib.sha1(course_id).hexdigest()
        base_url = "/".join([database, index, course_hash])
    full_url = "/".join([base_url, "_search?q=searchable_text:"])
    log.debug(full_url)
    context = {}
    response = requests.get(full_url+query+"&size=10000")
    data = SearchResults(request, response)
    data.filter("course", request.GET.get("selected_course"))
    data.filter("org", request.GET.get("selected_org"))
    org_histogram = data.get_counter("org")
    course_histogram = data.get_counter("course")
    data.sort_results()
    context.update({"results": data.has_results})
    correction = spell_check(query)
    results_pages = Paginator(data.entries, results_per_page)

    data = proper_page(results_pages, page)
    context.update({
        "data": data,
        "next_page": next_link(request, data),
        "prev_page": prev_link(request, data),
        "search_correction_link": search_correction_link(request, correction),
        "spelling_correction": correction,
        "org_histogram": org_histogram,
        "course_histogram": course_histogram,
        "selected_course": request.GET.get("selected_course", ""),
        "selected_org": request.GET.get("selected_org", "")
    })
    return context


def query_reduction(query, stopwords):
    return [word.lower() for word in query.split() if word not in stopwords]


def proper_page(pages, index):
    correct_page = pages.page(1)
    try:
        correct_page = pages.page(index)
    except PageNotAnInteger:
        correct_page = pages.page(1)
    except EmptyPage:
        correct_page = pages.page(pages.num_pages)
    return correct_page


def next_link(request, paginator):
    return request.path+"?s="+request.GET.get("s", "") + \
        "&content=" + request.GET.get("content", "transcript") + "&page="+str(paginator.next_page_number())


def prev_link(request, paginator):
    return request.path+"?s="+request.GET.get("s", "") + \
        "&content=" + request.GET.get("content", "transcript") + "&page="+str(paginator.previous_page_number())


def search_correction_link(request, term, page="1"):
    if term:
        return request.path+"?s="+term+"&page="+page+"&content="+request.GET.get("content", "transcript")
    else:
        return request.path+"?s="+request.GET["s"]+"&page"+page+"&content="+request.GET.get("content", "transcript")


def spell_check(query, pyenchant_dictionary_file="common/djangoapps/search/pyenchant_corpus.txt", stopwords=set()):
    """Returns corrected version with attached html if there are suggested corrections."""
    dictionary = enchant.request_pwl_dict(pyenchant_dictionary_file)
    words = query_reduction(query, stopwords)
    try:
        possible_corrections = [dictionary.suggest(word)[0] for word in words]
    except IndexError:
        return False
    if possible_corrections == words:
        return None
    else:
        return " ".join(possible_corrections)
