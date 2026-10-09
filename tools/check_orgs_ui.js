/* Admin → Organizations: the GAIUS team appoints every organization's admins.

     1. Organizations waiting for an admin are listed first, with Make admin.
     2. Unfinished sign-ups are listed, and Remove asks before it acts.
     3. Appoint an admin: choose a state, then an agency, then the person.
     4. All organizations, searchable, each with its people and roles.
     5. Nothing from any organization's framework is on the screen.
     6. Somebody who is not on the team is told so, and sees nothing.

   Every server answer is held here, so nothing is written.
       node tools/check_orgs_ui.js
*/

const { boot, settle, until, reporter, openView } = require("./_jsdom_boot");

const ORGS = {
  ok: true, waiting: 1,
  organizations: [
    { agency: "sc.scdor", organization: "South Carolina Department of Revenue", state: "SC",
      status: "active", created_at: "2026-09-25T12:00:00+00:00", test: false, needs_admin: true,
      people: [{ email: "pat.lee@dor.sc.gov", name: "Pat Lee", title: "Director", role: "member", added_at: "" }] },
    { agency: "sc.des", organization: "South Carolina Department of Environmental Services", state: "SC",
      status: "active", created_at: "2026-08-21T12:00:00+00:00", test: false, needs_admin: false,
      people: [{ email: "brett.butz@des.sc.gov", name: "Brett Butz", title: "AI Strategist", role: "admin", added_at: "" },
               { email: "lokesh.dandu@des.sc.gov", name: "lokesh dandu", title: "tester", role: "member", added_at: "" }] },
    { agency: "iia.test", organization: "DEMO agency", state: "IIA", status: "active",
      created_at: "", test: true, needs_admin: false,
      people: [{ email: "dev@iiac.ai", name: "Dev", title: "", role: "admin", added_at: "" }] },
  ],
  pending: [{ email: "anna.grondin@env.nm.gov", name: "Anna Grondin", title: "Chief", agency: "nm.env",
              organization: "New Mexico Environment Department", status: "pending_code", signin: false,
              started: "2026-09-16T12:00:00+00:00", attempts: 0, code_expired: true }],
};

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const view = () => doc.getElementById("view");
  const posts = [];
  let refuse = false;
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes("/api/admin/")) {
      const body = opts && opts.body ? JSON.parse(opts.body) : null;
      if (body) posts.push([u.replace(/^.*\/api/, "/api").split("?")[0], body]);
      const answer = refuse ? { ok: false, error: "This is for the GAIUS team." }
        : u.includes("/pending/remove") ? { ...ORGS, pending: [], says: "The sign-up for Anna Grondin is removed." }
        : u.includes("/member/role") ? { ...ORGS, waiting: 0, says: "Pat Lee is an admin now.",
            organizations: ORGS.organizations.map((o) => o.agency === "sc.scdor"
              ? { ...o, needs_admin: false, people: o.people.map((p) => ({ ...p, role: "admin" })) } : o) }
        : u.includes("/appoint") ? { ...ORGS, says: "jo.doe@dor.sc.gov is an admin of South Carolina Department of Revenue." }
        : ORGS;
      return { ok: true, status: 200, json: async () => answer };
    }
    return real(url, opts);
  };
  if (window.closeLauncher) window.closeLauncher();

  console.log("the screen");
  check("it opens", await openView(window, "organizations", /Waiting for an admin/));
  const text = () => view().textContent.replace(/\s+/g, " ");
  check("waiting for an admin comes first, with the organization", /Waiting for an admin \(1\).*Department of Revenue/.test(text()));
  check("unfinished sign-ups are listed", /Unfinished sign-ups \(1\)/.test(text()) && /Anna Grondin/.test(text())
    && /code expired/.test(text()));
  check("test organizations are hidden by default", !/DEMO agency/.test(text()));
  check("it says it shows people, never a framework", /never an organization's framework/.test(text()));

  console.log("\nmaking an admin");
  const make = view().querySelector('[data-setrole="admin"][data-email="pat.lee@dor.sc.gov"]');
  make.click();
  await settle(100);
  const veil = () => (doc.getElementById("confirmVeil") || {}).textContent || "";
  check("it asks first, naming the organization", /Make Pat Lee an admin of South Carolina Department of Revenue\?/.test(veil()));
  check("nothing is sent before the answer", posts.length === 0);
  doc.getElementById("confirmYes").click();
  await until(() => posts.length === 1);
  check("then it is sent for that organization", posts[0][0] === "/api/admin/member/role"
    && posts[0][1].agency === "sc.scdor" && posts[0][1].role === "admin", JSON.stringify(posts));
  await settle(200);
  check("and the screen updates", /Waiting for an admin \(0\)/.test(text()) && /Pat Lee is an admin now/.test(text()));

  console.log("\nremoving a sign-up");
  view().querySelector("[data-pending]").click();
  await settle(100);
  check("it asks first", /Remove the sign-up for Anna Grondin\?/.test(veil()));
  doc.getElementById("confirmYes").click();
  await until(() => posts.length === 2);
  check("then it is removed", posts[1][0] === "/api/admin/pending/remove"
    && posts[1][1].email === "anna.grondin@env.nm.gov");
  check("and the list redraws", await until(() => /Unfinished sign-ups \(0\)/.test(text())));

  console.log("\nappointing an admin");
  const st = doc.getElementById("appState");
  check("the states load", await until(() => st.options.length > 50), `${st.options.length}`);
  st.value = "SC"; st.dispatchEvent(new window.Event("change"));
  const ag = doc.getElementById("appAgency");
  check("choosing a state lists its agencies", !ag.disabled && ag.options.length > 100);
  check("registered ones are marked", [...ag.options].some((o) => /Revenue \(registered\)/.test(o.textContent)));
  doc.getElementById("appGo").click();
  await settle(100);
  check("an incomplete form is refused in words", !doc.getElementById("appErr").hidden && posts.length === 2);
  ag.value = "sc.scdor";
  doc.getElementById("appName").value = "Jo Doe";
  doc.getElementById("appTitle").value = "Deputy";
  doc.getElementById("appEmail").value = "jo.doe@dor.sc.gov";
  doc.getElementById("appGo").click();
  await until(() => posts.length === 3);
  check("it sends the agency and the person", posts[2][0] === "/api/admin/appoint"
    && posts[2][1].agency === "sc.scdor" && posts[2][1].email === "jo.doe@dor.sc.gov");
  await settle(200);
  check("and says what happened", /is an admin of South Carolina Department of Revenue/.test(text()));

  console.log("\nall organizations");
  const find = doc.getElementById("orgFind");
  find.value = "lokesh"; find.dispatchEvent(new window.Event("input"));
  await settle(100);
  const rows = [...view().querySelectorAll("details.org-row")];
  check("search finds the organization a person is in", rows.length === 1
    && /Environmental Services/.test(rows[0].textContent) && /admin: Brett Butz/.test(rows[0].textContent));
  check("focus stays in the search box", doc.activeElement === doc.getElementById("orgFind"));
  doc.getElementById("orgTests").click();
  doc.getElementById("orgFind").value = ""; doc.getElementById("orgFind").dispatchEvent(new window.Event("input"));
  await settle(100);
  check("test organizations can be shown", /DEMO agency/.test(text()));

  const unnamed = [...view().querySelectorAll("input, select, button")].filter((c) =>
    !(c.id && doc.querySelector(`label[for="${c.id}"]`)) && !c.closest("label")
    && !(c.tagName === "BUTTON" && (c.getAttribute("aria-label") || c.textContent.trim())));
  check("every control has a name", unnamed.length === 0, unnamed.map((c) => c.id || c.outerHTML.slice(0, 60)).join(" "));
  check("no framework content on the screen", !/Module One|Purpose|Who decides|DRAFT/.test(text()));

  console.log("\nsomebody not on the team");
  refuse = true;
  await window.go("organizations");
  await settle(400);
  check("is told so, and sees nothing", /This is for the GAIUS team/.test(text()) && !/Anna Grondin|Brett Butz/.test(text()));

  window.fetch = real;
  finish(errors, "the GAIUS team appoints admins and clears unfinished sign-ups, people only");
}

main().catch((e) => { console.error(e); process.exit(1); });
