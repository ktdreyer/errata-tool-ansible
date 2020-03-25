from errata_tool_variant import scrape_error_explanation


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
