from errata_tool_variant import scrape_error_explanation
from errata_tool_variant import scrape_error_message


class FakeErrorResponse(object):
    pass


def test_scrape_error_explanation():
    response = FakeErrorResponse()
    response.text = '''
    <div id="errorExplanation" class="errorExplanation">
    <h2>1 error prohibited this variant from being saved</h2>
    <p>There were problems with the following fields:</p>
    <ul><li>Variant push targets is invalid</li></ul></div>
'''
    result = scrape_error_explanation(response)
    expected = ['Variant push targets is invalid']
    assert result == expected


def test_scrape_error_message():
    response = FakeErrorResponse()
    response.text = '''
    <div class="site_message">
    <div class="alert alert-error">
    <img src="/images/icon_alert.gif"
    style="vertical-align:middle;"/>&nbsp;<b>Error</b>
    <div id="error-message" class="just_text pre-wrap">
    You do not have permission to edit CPE, need a secalert role
    </div></div>
    </div>
    '''
    result = scrape_error_message(response)
    expected = ['You do not have permission to edit CPE, need a secalert role']
    assert result == expected
