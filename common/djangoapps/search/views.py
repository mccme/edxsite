from mitxmako.shortcuts import render_to_string
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse
from models import SearchResults

import requests
import enchant

CONTENT_TYPES = ("transcript", "problem", "pdf")


def search(request):
    context = {}
    results_string = ""
    if request.GET:
        results_string = find(request)
        context.update({"old_query": request.GET.get('s', "")})
    context.update({"previous": request.GET})
    search_bar = render_to_string("search_templates/search.html", context)
    full_html = render_to_string("search_templates/wrapper.html", {"body": search_bar+results_string})
    return HttpResponse(full_html)


def find(request, database="http://127.0.0.1:9200",
         field="searchable_text", max_result=100):
    get_content = lambda request, content: content+"-index" if request.GET.get(content, False) else None
    query = request.GET.get("s", "*.*")
    page = request.GET.get("page", 1)
    results_per_page = request.GET.get("results", 15)
    index = ",".join(filter(None, [get_content(request, content) for content in CONTENT_TYPES]))
    full_url = "/".join([database, index, "_search?q="+field+":"])
    context = {}
    response = requests.get(full_url+query+"&size="+str(max_result))
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
        "data": data, "next_page": next_link(request, data), "prev_page": prev_link(request, data),
        "search_correction_link": search_correction_link(request, correction),
        "spelling_correction": correction, "org_histogram": org_histogram,
        "course_histogram": course_histogram, "selected_course": request.GET.get("selected_course", ""),
        "selected_org": request.GET.get("selected_org", "")})
    return render_to_string("search_templates/results.html", context)


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