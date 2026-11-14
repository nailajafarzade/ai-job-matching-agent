from app.collectors.text import html_to_text


def test_html_to_text_preserves_sections_lists_and_decodes_entities():
    html = """
    <h2>Requirements</h2>
    <p>Build &amp; test&nbsp;services.</p>
    <ul><li><strong>Java</strong></li><li>Spring Boot</li><li><p>PostgreSQL</p></li></ul>
    <div>Apply <b>now</b></div><br>
    <h3>Benefits:</h3>
    """

    assert html_to_text(html) == (
        "Requirements:\nBuild & test services.\n- Java\n- Spring Boot\n- PostgreSQL\nApply now\nBenefits:"
    )


def test_html_to_text_removes_empty_lines_and_adds_heading_colon():
    assert html_to_text("<h1>About us</h1><p> </p><p>Work remotely.</p>") == (
        "About us:\nWork remotely."
    )
