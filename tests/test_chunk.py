from pinpoint_docs.chunk import page_url, split_page

PAGE = """# Body { #body }

Intro text.

## Declare it { #declare-it }

/// tip | Good to know
Use a model.
///

```bash
# not a heading
```

### Deeper { #deeper }

More.
"""


def test_split_page():
    chunks = split_page("tutorial/body.md", PAGE)
    assert [c["section"] for c in chunks] == ["Body", "Declare it", "Deeper"]
    assert chunks[1]["url"] == "https://fastapi.tiangolo.com/tutorial/body/#declare-it"
    assert "Good to know:" in chunks[1]["text"]
    assert "///" not in chunks[1]["text"]
    assert "# not a heading" in chunks[1]["text"]
    assert all(c["title"] == "Body" for c in chunks)


def test_page_url():
    assert page_url("index.md") == "https://fastapi.tiangolo.com/"
    assert page_url("tutorial/index.md") == "https://fastapi.tiangolo.com/tutorial/"
    assert page_url("async.md") == "https://fastapi.tiangolo.com/async/"
