"""Styles for the bug widget, the form and the queue."""
import pathlib

CSS = """
/* --------------------------------------------------------- the bug widget

   Sits over the bottom-right corner, which is sometimes exactly where the
   thing being reported is — hence the grip. Position is remembered so it does
   not spring back on every reload, and clamped on restore so a spot saved on a
   wide monitor cannot put it off the edge of a laptop. */
.bug-dock {
  position: fixed; right: 18px; bottom: 18px; z-index: 250;
  display: flex; align-items: center; gap: 2px;
  border-radius: 22px; background: var(--chrome); color: #fff;
  box-shadow: 0 6px 20px rgba(0,0,0,.28);
}
.bug-dock.dragging { opacity: .85; box-shadow: 0 10px 28px rgba(0,0,0,.4); }
.bug-grip {
  padding: 8px 4px 8px 11px; color: rgba(255,255,255,.5);
  cursor: grab; font-size: 13px; line-height: 1;
}
.bug-grip:active { cursor: grabbing; }
.bug-open {
  padding: 9px 15px 9px 6px; color: #fff; font-size: 12.5px; font-weight: 600;
  border-radius: 0 22px 22px 0;
}
.bug-open:hover { background: rgba(255,255,255,.1); }

.bug-modal {
  position: fixed; inset: 0; z-index: 260; display: grid; place-items: center;
  background: rgba(6, 18, 24, .55); padding: 20px;
}
.bug-card {
  width: min(620px, 100%); max-height: 88vh; overflow-y: auto;
  background: var(--surface); border-radius: 14px; padding: 22px 24px;
  box-shadow: 0 24px 60px rgba(0,0,0,.4);
}

/* Shown before sending, not after. Somebody handing over a minute of their
   session deserves to see exactly what that means first. */
.bug-attached { margin-top: 14px; }
.bug-attached summary {
  cursor: pointer; font-size: 12px; font-weight: 600; color: var(--accent-text);
}
.bug-context {
  display: flex; flex-wrap: wrap; gap: 6px 16px; margin: 10px 0;
  font-size: 11px; color: var(--muted);
}
.bug-context b { color: var(--ink); font-weight: 600; margin-right: 4px; }
.bug-events {
  margin: 8px 0 0; padding: 8px 10px; list-style: none; max-height: 220px;
  overflow-y: auto; border-radius: 7px; background: var(--surface-2);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10.5px;
  line-height: 1.55;
}
.bug-events li { padding: 2px 0; word-break: break-word; }
.bug-events b {
  display: inline-block; min-width: 58px; color: var(--muted);
  text-transform: uppercase; font-size: 9px; letter-spacing: .6px;
}
.bug-events i { font-style: normal; color: var(--accent-text); margin-right: 5px; }
.bug-events .ev-error b { color: var(--alert); }
.bug-events .ev-warn  b { color: var(--warn); }

/* ------------------------------------------------------------- the queue */

.bug-filters { display: flex; flex-wrap: wrap; gap: 5px; }
.bug-filters .btn { padding: 4px 10px; font-size: 11px; }
.bug-filters .btn.on { background: var(--chrome); color: #fff; }
.bug-ticket { border-left: 3px solid var(--line); }
.bug-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px; font-weight: 700; margin-right: 8px;
}
.bug-said { margin: 10px 0 0; font-size: 12.5px; line-height: 1.55; }
.bug-said b { color: var(--accent-text); }
.bug-reply {
  margin-top: 10px; padding: 9px 11px; border-radius: 7px;
  background: var(--surface-2); font-size: 12px; line-height: 1.5;
}
.bug-reply.team { border-left: 2px solid var(--ok); }
.bug-reply p { margin: 4px 0 0; }
.bug-ticket select, .bug-ticket input[type="text"] {
  padding: 7px 9px; border-radius: 7px; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink); font-size: 12px;
}
"""

p = pathlib.Path("app/web/assets/app.css")
p.write_text(p.read_text(encoding="utf-8") + CSS, encoding="utf-8")
print("bug styles appended")
