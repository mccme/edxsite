# disable missing docstring
#pylint: disable=C0111

from lettuce import world
from nose.tools import assert_equal
from terrain.steps import reload_the_page


@world.absorb
def create_component_instance(step, component_button_css, category,
                              expected_css, boilerplate=None,
                              has_multiple_templates=True):

    click_new_component_button(step, component_button_css)

    if has_multiple_templates:
        click_component_from_menu(category, boilerplate, expected_css)

    assert_equal(
        1,
        len(world.css_find(expected_css)),
        "Component instance with css {css} was not created successfully".format(css=expected_css))


@world.absorb
def click_new_component_button(step, component_button_css):
    step.given('I have clicked the new unit button')
    world.css_click(component_button_css)


@world.absorb
def click_component_from_menu(category, boilerplate, expected_css):
    """
    Creates a component from `instance_id`. For components with more
    than one template, clicks on `elem_css` to create the new
    component. Components with only one template are created as soon
    as the user clicks the appropriate button, so we assert that the
    expected component is present.
    """
    if boilerplate:
        elem_css = "a[data-category='{}'][data-boilerplate='{}']".format(category, boilerplate)
    else:
        elem_css = "a[data-category='{}']:not([data-boilerplate])".format(category)
    elements = world.css_find(elem_css)
    assert_equal(len(elements), 1)
    world.css_click(elem_css)


@world.absorb
def edit_component_and_select_settings():
    world.css_click('a.edit-button')
    world.css_click('#settings-mode')


@world.absorb
def verify_setting_entry(setting, display_name, value, explicitly_set):
    assert_equal(display_name, setting.find_by_css('.setting-label')[0].value)
    assert_equal(value, setting.find_by_css('.setting-input')[0].value)
    settingClearButton = setting.find_by_css('.setting-clear')[0]
    assert_equal(explicitly_set, settingClearButton.has_class('active'))
    assert_equal(not explicitly_set, settingClearButton.has_class('inactive'))


@world.absorb
def verify_all_setting_entries(expected_entries):
    settings = world.browser.find_by_css('.wrapper-comp-setting')
    assert_equal(len(expected_entries), len(settings))
    for (counter, setting) in enumerate(settings):
        world.verify_setting_entry(
            setting, expected_entries[counter][0],
            expected_entries[counter][1], expected_entries[counter][2]
        )


@world.absorb
def save_component_and_reopen(step):
    world.css_click("a.save-button")
    # We have a known issue that modifications are still shown within the edit window after cancel (though)
    # they are not persisted. Refresh the browser to make sure the changes WERE persisted after Save.
    reload_the_page(step)
    edit_component_and_select_settings()


@world.absorb
def cancel_component(step):
    world.css_click("a.cancel-button")
    # We have a known issue that modifications are still shown within the edit window after cancel (though)
    # they are not persisted. Refresh the browser to make sure the changes were not persisted.
    reload_the_page(step)


@world.absorb
def revert_setting_entry(label):
    get_setting_entry(label).find_by_css('.setting-clear')[0].click()


@world.absorb
def get_setting_entry(label):
    settings = world.browser.find_by_css('.wrapper-comp-setting')
    for setting in settings:
        if setting.find_by_css('.setting-label')[0].value == label:
            return setting
    return None
