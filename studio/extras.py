"""Owner-chosen extras (steps, heart rate, ...): the tick boxes on the job form and the builder's brief.

The builder draws each extra in the selected watch's own design language; the engine adds the live
value and an on/off switch in the watch's customise screen (engine/CONTRACT.md, "Extras").
"""
from __future__ import annotations

# id -> (tick-box label, short hint shown under it)
OPTIONS = {
    'steps': ('Steps', 'today\'s step count'),
    'heartRate': ('Heart rate', 'live BPM'),
    'battery': ('Battery', 'watch battery %'),
    'weekday': ('Day of week', 'MON, TUE...'),
    'date': ('Date', 'day of the month'),
    'weather': ('Weather', 'temperature from your phone'),
}


def parse(values) -> str:
    """Form checkbox values -> stored comma list, in OPTIONS order."""
    chosen = set(values or [])
    return ','.join(k for k in OPTIONS if k in chosen)


def ids(stored: str | None) -> list[str]:
    return [k for k in (stored or '').split(',') if k in OPTIONS]


def labels(stored: str | None) -> str:
    return ', '.join(OPTIONS[k][0] for k in ids(stored))


def brief(stored: str | None, face_has_extras: bool) -> str:
    """The builder's instructions for this round ('' when there is nothing to say)."""
    want = ids(stored)
    if not want:
        if face_has_extras:
            return ('EXTRAS: the owner no longer wants any extras. Remove manifest.extras, build().extras / '
                    'aodExtras and any hand with an `extra` field.')
        return ''
    names = ', '.join(f'{OPTIONS[k][0]} (source "{k}")' for k in want)
    return f'''OWNER-CHOSEN EXTRAS: {names}.
Add each one to manifest.extras exactly as engine/CONTRACT.md "Extras" describes; remove any extra not in this list.
They must look as if the watchmaker designed them for THIS watch, never like a widget stuck on top:
- Reuse the dial's own vocabulary: its fonts, ink and accent colours, printed-label style, window frames,
  register rims, tick style and finishing. A digital readout sits in a window or aperture styled like the
  watch's own date window; a gauge is a small register styled like its existing subdials, with a hand that
  matches its other register hands.
- If the real watch already has a fitting element (a date window, a register, a power-reserve arc), wire
  the extra into it instead of adding a second one (e.g. a steps gauge hand in an existing 30-min register).
- RECOGNISABLE AT A GLANCE: the owner must be able to point at each extra in <v>_onwatch.png without being
  told where it is. Give every extra a clear label in the dial's printed-label style (e.g. "STEPS", "BPM",
  a small icon only if the dial uses icons), >= 12 px, never under a parked hand, the hub or a lume dot.
  A hand repurposed in an existing register alone is NOT enough: label the register for its new job, and
  add a live number (`text`) where there is room (e.g. "6240" in a small window styled like the date).
- Place extras where the real dial has empty space and keep its symmetry and balance; never cover indices,
  numerals or the existing date. Keep them quieter than the time: small, ink-coloured, accent sparingly.
- Text: readable at 480 px (>= 12 px), short (no "STEPS:" prefixes unless the dial already prints labels
  like that). Weekday labels in the case and language that suit the dial (`text.labels`).
- Always-On: show an extra only if it stays within the lit-pixel budget, dimmed like the other static parts.
- The photo-pose render (<v>.png) hides extras on purpose; judge them on <v>_onwatch.png and <v>_alt.png.'''
