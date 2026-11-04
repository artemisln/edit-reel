"""Per-product beat file. Copy this, edit the beats, keep the whole run under 90 seconds.

Each beat is one function taking the Stage. Its docstring is the VO line it serves,
and the comment after it is what MUST be visibly true on screen at that moment.
"""

NAME      = "example"                      # output filename
START_URL = "https://www.wikipedia.org"    # loaded BEFORE recording starts


def search_box(st):
    """L01 'you just describe what you want'"""
    st.click("#searchInput")
    st.type("Ada Lovelace")
    st.hold(1.5)          # MUST be true: the typed text is visible in the box


def submit(st):
    """L02 'and it finds it'"""
    st.press("Enter")
    st.hold(3.0)          # MUST be true: the result page has actually rendered


def show_detail(st):
    """L03 'with everything laid out'"""
    st.scroll(600)
    st.hold(2.5)          # MUST be true: the detail section is on screen, not mid-scroll


BEATS = [search_box, submit, show_detail]
