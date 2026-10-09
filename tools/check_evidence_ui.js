/* Does a passage from the organization's own documents show, and use, as it
   should on the Framework screen?

     1. The quote, the file it came from and the words it shares are shown,
        in a labelled region, apart from the answer controls.
     2. "Use this answer" sends the answer with its source named — and
        nothing else is answered.
     3. Where a passage points at no one choice, it is shown to read and no
        button offers to fill anything in.

   Holds the save rather than sending it, so nothing is written.
       node tools/check_evidence_ui.js
*/

const { boot, settle, reporter } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const sent = [];
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    if (String(url).includes("/api/versions/answer")) {
      sent.push(JSON.parse(opts.body));
      return { ok: true, status: 200, json: async () => ({ ok: true }) };
    }
    if (String(url).includes("/api/module?step=")) {
      return { ok: true, status: 200, json: async () => ({ questions: [Q] }) };
    }
    return real(url, opts);
  };

  const Q = {
    key: "why.conflict", number: "11.4", kind: "single",
    prompt: "When your rules and a state or federal rule disagree, which one wins?",
    options: [{ value: "stricter", label: "Whichever is stricter" },
              { value: "external", label: "The state or federal rule" }],
    evidence: [{
      file: "county-aup.docx", kind: "Acceptable use", paragraph: 4,
      quote: "Where state or federal rules conflict with this policy, whichever is stricter controls.",
      matched: ["federal", "state"],
      suggest: { value: "stricter", labels: ["Whichever is stricter"] },
    }, {
      file: "county-aup.docx", kind: "Acceptable use", paragraph: 9,
      quote: "State and federal partners are consulted on major changes.",
      matched: ["federal", "state"], suggest: null,
    }],
  };

  // FB is the page's own const and starts with answers = {}; nothing to set.
  const host = doc.createElement("div");
  doc.body.appendChild(host);
  host.appendChild(window.fbQuestion(Q));
  window.wireQuestion(Q);
  await settle(100);

  console.log("the passage");
  const region = host.querySelector(".fb-evidence");
  check("it sits in a labelled region", !!region && !!doc.getElementById(region.getAttribute("aria-labelledby")));
  check("the quote is shown", /whichever is stricter controls/.test(region.textContent));
  check("with the file it came from", /county-aup\.docx/.test(region.textContent));
  check("and the words it shares", /shares the words federal, state/.test(region.textContent));
  check("it says what it would fill in", /This reads like: Whichever is stricter/.test(region.textContent));
  check("it says nothing is answered for you", /Nothing is answered for you/.test(region.textContent));
  const buttons = region.querySelectorAll("[data-use]");
  check("only the clear passage offers to fill anything in", buttons.length === 1);
  check("the unclear one says to read and choose", /Read it and choose/.test(region.textContent));

  console.log("\nusing it");
  buttons[0].click();
  await settle(400);
  check("one answer is sent", sent.length === 1, JSON.stringify(sent));
  check("the choice the passage named", sent[0] && sent[0].value === "stricter");
  check("with its source", sent[0] && sent[0].from_document &&
    sent[0].from_document.file === "county-aup.docx" && sent[0].from_document.paragraph === 4);

  finish(errors, "passages show with their source, and using one records it");
}

main().catch((e) => { console.error(e); process.exit(1); });
