import logging
import urllib
import lxml
import re

from django.conf import settings
from django.core.context_processors import csrf
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from mitxmako.shortcuts import render_to_response, render_to_string
from django_future.csrf import ensure_csrf_cookie
from django.views.decorators.cache import cache_control
from courseware.module_render import toc_for_course, get_module_for_descriptor
from django.template import Context
from django.template.loader import get_template

from courseware.access import has_access
from courseware.courses import (get_courses, get_course_with_access)
from courseware.masquerade import setup_masquerade
from courseware.model_data import ModelDataCache
from student.models import CourseEnrollment
from courseware.models import StudentModule

from xmodule.modulestore.django import modulestore
from xmodule.modulestore import Location

log = logging.getLogger("mitx.courseware")

template_imports = {'urllib': urllib}


# def test(request):
#     user = User.objects.prefetch_related("groups").get(id=request.user.id)
#     request.user = user

#     course_list = get_courses(user, request.META.get('HTTP_HOST'))

#     all_modules = [get_module(request, user, course) for course in course_list if registered_for_course(course, user)]
#     child_modules = []
#     for module in all_modules:
#         child_modules.extend(module.get_children())
#     bottom_modules = []
#     for module in child_modules:
#         bottom_modules.extend(module.get_children())
#     asset_divs = get_asset_div(convert_to_valid_html(bottom_modules[0].get_html()))
#     kwargs = {'path': 'content-mit-802x/subs', 'document_root': path(u'/home/slater/edx_all/staticfiles')}
#     #strings = [get_transcript_directory(request, lxml.html.tostring(div)) for div in asset_divs]
#     strings = get_transcript_directory(kwargs)
#     search_template = get_template('search.html')
#     html = search_template.render(Context({'render_test': strings}))
#     return HttpResponse(html)

def test(request):
    user = User.objects.prefetch_related("groups").get(id=request.user.id)
    request.user = user

    course_list = get_courses(user, request.META.get('HTTP_HOST'))
    test_course = course_list[1]
    staff_access = has_access(user, test_course, 'staff')
    #all_modules = [get_module(request, user, course) for course in course_list if registered_for_course(course, user)]
    masq = setup_masquerade(request, staff_access)
    model_data_cache = ModelDataCache.cache_for_descriptor_descendents(test_course.id, user, test_course, depth=2)
    context = {
        'csrf': csrf(request)['csrf_token'],
        'COURSE_TITLE': test_course.display_name_with_default,
        'accordion': render_accordion(request, test_course, 'Week_1', None, model_data_cache),
        'course': test_course,
        'init': '',
        'content': '',
        'staff_access': staff_access,
        'masquerade': masq,
        'xqa_server': settings.MITX_FEATURES.get('USE_XQA_SERVER', 'http://xqa:server@content-qa.mitx.mit.edu/xqa')
    }
    result = render_to_response('courseware/courseware.html', context)
    search_template = get_template('search.html')
    course_module = get_module_for_descriptor(user, request, test_course, model_data_cache, test_course.id)

    course_descriptors = test_course.get_children()
    test_descriptor = course_descriptors[0]
    chapter_modules = course_module.get_children()
    test_module = chapter_modules[0]

    prev_section = get_current_child(test_module)
    test_module = get_module(request, user, test_course)
    if prev_section is None:
        # Something went wrong -- perhaps this chapter has no sections visible to the user
        raise Http404

    prev_section_url = reverse('courseware_section', kwargs={'course_id': test_course.id,
                                                             'chapter': test_descriptor.url_name,
                                                             'section': prev_section.url_name})
    context['content'] = render_to_string('courseware/welcome-back.html',
                                          {'course': test_course,
                                           'chapter_module': test_module,
                                           'prev_section': prev_section,
                                           'prev_section_url': prev_section_url})

    result = HttpResponse(search_template.render(Context({'render_test': context})))

    #result = render_to_response('courseware/courseware.html', context)

    return result


def registered_for_course(course, user):
    """
    Return CourseEnrollment if user is registered for course, else False
    """
    if user is None:
        return False
    if user.is_authenticated():
        return CourseEnrollment.objects.filter(user=user, course_id=course.id).exists()
    else:
        return False


def get_children(course):
    """Returns the children of a given course"""
    attributes = [child.location for child in course._child_instances]
    return attributes


def convert_to_valid_html(html):
    replacement = {"&lt;": "<", "&gt;": ">", "&#34;": "\"", "&#39;": "'"}
    for i, j in replacement.iteritems():
        html = html.replace(i, j)
    return html


def get_asset_div(html_page):
    return lxml.html.find_class(html_page, "video")


def get_module(request, user, course):
    model_data_cache = ModelDataCache.cache_for_descriptor_descendents(course.id, user, course, depth=2)
    course_module = get_module_for_descriptor(user, request, course, model_data_cache, course.id)
    return course_module


def get_youtube_code(module_html):
    youtube_snippet = re.sub(r'(.*?)(1\.0:)(.*?)(,1\.25)(.*)', r'\3', module_html)
    sliced_youtube_code = youtube_snippet[:youtube_snippet.find('\n')]
    return sliced_youtube_code


def get_transcript_directory(module_html):
    directory_snippet = re.sub(r'(.*?)(data-caption-asset-path=\")(.*?)(\">.*)', r'\3', module_html)
    sliced_directory = directory_snippet[:directory_snippet.find('\n')]
    return sliced_directory


def get_current_child(xmodule):
    """
    Get the xmodule.position's display item of an xmodule that has a position and
    children.  If xmodule has no position or is out of bounds, return the first child.
    Returns None only if there are no children at all.
    """
    if not hasattr(xmodule, 'position'):
        return None

    if xmodule.position is None:
        pos = 0
    else:
        # position is 1-indexed.
        pos = xmodule.position - 1

    children = xmodule.get_display_items()
    if 0 <= pos < len(children):
        child = children[pos]
    elif len(children) > 0:
        # Something is wrong.  Default to first child
        child = children[0]
    else:
        child = None
    return child


def check_for_active_timelimit_module(request, course_id, course):
    """
    Looks for a timing module for the given user and course that is currently active.
    If found, returns a context dict with timer-related values to enable display of time remaining.
    """
    context = {}

    # TODO (cpennington): Once we can query the course structure, replace this with such a query
    timelimit_student_modules = StudentModule.objects.filter(student=request.user, course_id=course_id, module_type='timelimit')
    if timelimit_student_modules:
        for timelimit_student_module in timelimit_student_modules:
            # get the corresponding section_descriptor for the given StudentModel entry:
            module_state_key = timelimit_student_module.module_state_key
            timelimit_descriptor = modulestore().get_instance(course_id, Location(module_state_key))
            timelimit_module_cache = ModelDataCache.cache_for_descriptor_descendents(course.id, request.user,
                                                                                     timelimit_descriptor, depth=None)
            timelimit_module = get_module_for_descriptor(request.user, request, timelimit_descriptor,
                                                         timelimit_module_cache, course.id, position=None)
            if timelimit_module is not None and timelimit_module.category == 'timelimit' and \
                    timelimit_module.has_begun and not timelimit_module.has_ended:
                location = timelimit_module.location
                # determine where to go when the timer expires:
                if timelimit_descriptor.time_expired_redirect_url is None:
                    raise Http404("no time_expired_redirect_url specified at this location: {} ".format(timelimit_module.location))
                context['time_expired_redirect_url'] = timelimit_descriptor.time_expired_redirect_url
                # Fetch the remaining time relative to the end time as stored in the module when it was started.
                # This value should be in milliseconds.
                remaining_time = timelimit_module.get_remaining_time_in_ms()
                context['timer_expiration_duration'] = remaining_time
                context['suppress_toplevel_navigation'] = timelimit_descriptor.suppress_toplevel_navigation
                return_url = reverse('jump_to', kwargs={'course_id': course_id, 'location': location})
                context['timer_navigation_return_url'] = return_url
    return context


def update_timelimit_module(user, course_id, model_data_cache, timelimit_descriptor, timelimit_module):
    """
    Updates the state of the provided timing module, starting it if it hasn't begun.
    Returns dict with timer-related values to enable display of time remaining.
    Returns 'timer_expiration_duration' in dict if timer is still active, and not if timer has expired.
    """
    context = {}
    # determine where to go when the exam ends:
    if timelimit_descriptor.time_expired_redirect_url is None:
        raise Http404("No time_expired_redirect_url specified at this location: {} ".format(timelimit_module.location))
    context['time_expired_redirect_url'] = timelimit_descriptor.time_expired_redirect_url

    if not timelimit_module.has_ended:
        if not timelimit_module.has_begun:
            # user has not started the exam, so start it now.
            if timelimit_descriptor.duration is None:
                raise Http404("No duration specified at this location: {} ".format(timelimit_module.location))
            # The user may have an accommodation that has been granted to them.
            # This accommodation information should already be stored in the module's state.
            timelimit_module.begin(timelimit_descriptor.duration)

        # the exam has been started, either because the student is returning to the
        # exam page, or because they have just visited it.  Fetch the remaining time relative to the
        # end time as stored in the module when it was started.
        context['timer_expiration_duration'] = timelimit_module.get_remaining_time_in_ms()
        # also use the timed module to determine whether top-level navigation is visible:
        context['suppress_toplevel_navigation'] = timelimit_descriptor.suppress_toplevel_navigation
    return context


def save_child_position(seq_module, child_name):
    """
    child_name: url_name of the child
    """
    for position, c in enumerate(seq_module.get_display_items(), start=1):
        if c.url_name == child_name:
            # Only save if position changed
            if position != seq_module.position:
                seq_module.position = position


def render_accordion(request, course, chapter, section, model_data_cache):
    """
    Draws navigation bar. Takes current position in accordion as
    parameter.

    If chapter and section are '' or None, renders a default accordion.

    course, chapter, and section are the url_names.

    Returns the html string
    """

    # grab the table of contents
    user = User.objects.prefetch_related("groups").get(id=request.user.id)
    request.user = user  # keep just one instance of User
    toc = toc_for_course(user, request, course, chapter, section, model_data_cache)

    context = dict([('toc', toc),
                    ('course_id', course.id),
                    ('csrf', csrf(request)['csrf_token']),
                    ('show_timezone', course.show_timezone)] + template_imports.items())
    return render_to_string('courseware/accordion.html', context)


def redirect_to_course_position(course_module):
    """
    Return a redirect to the user's current place in the course.

    If this is the user's first time, redirects to COURSE/CHAPTER/SECTION.
    If this isn't the users's first time, redirects to COURSE/CHAPTER,
    and the view will find the current section and display a message
    about reusing the stored position.

    If there is no current position in the course or chapter, then selects
    the first child.

    """
    urlargs = {'course_id': course_module.descriptor.id}
    chapter = get_current_child(course_module)
    if chapter is None:
        # oops.  Something bad has happened.
        raise Http404("No chapter found when loading current position in course")

    urlargs['chapter'] = chapter.url_name
    if course_module.position is not None:
        return redirect(reverse('courseware_chapter', kwargs=urlargs))

    # Relying on default of returning first child
    section = get_current_child(chapter)
    if section is None:
        raise Http404("No section found when loading current position in course")

    urlargs['section'] = section.url_name
    return redirect(reverse('courseware_section', kwargs=urlargs))
