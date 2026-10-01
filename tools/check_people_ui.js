/* Does "People in your organization" work as a screen?

     1. An admin sees everybody, their addresses, and the Add a colleague
        form with the agency's email rule.
     2. Adding somebody puts them on the list, says what happens next, and
        sends nothing — the colleague signs in with their own code.
     3. A member sees names, titles and roles, no addresses and no form.

   Holds the add rather than sending it, so nothing is written.
       node tools/check_people_ui.js
*/

const { boot, settle, reporter } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const people = [
    { name: "Brett Butz", title: "AI Strategist", role: "Admin", email: "brett.butz@des.sc.gov", added_at: "2026-09-25T02:46:53+00:00" },
    { name: "lokesh dandu", title: "tester", role: "Member", email: "lokesh.dandu@des.sc.gov", added_at: "2026-08-21T12:17:19+00:00" },
  ];
  const sent = [];
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    if (String(url).includes("/api/agency/member")) {
      const body = JSON.parse(opts.body);
      sent.push(body);
      return { ok: true, status: 200, json: async () => ({ ok: true, is_admin: true, me: "brett.butz@des.sc.gov", domain: "des.sc.gov",
        people: [...people, { ...body, role: "Member", added_at: "2026-09-25T03:00:00+00:00" }],
        says: `${body.name} is on South Carolina Department of Environmental Services now. They sign in with their own work email and a code sent to it — nothing is sent to them from here.` }) };
    }
    return real(url, opts);
  };

  console.log("the owner");
  const host = doc.createElement("div"); doc.body.appendChild(host);
  host.appendChild(window.peoplePanel({ ok: true, is_admin: true, me: "brett.butz@des.sc.gov", domain: "des.sc.gov", admin_names: ["Brett Butz"], people },
    "South Carolina Department of Environmental Services"));
  const panel = () => doc.getElementById("peoplePanel");
  check("everybody is listed", /Brett Butz/.test(panel().textContent) && /lokesh dandu/.test(panel().textContent));
  check("with their addresses", /lokesh\.dandu@des\.sc\.gov/.test(panel().textContent));
  check("the form is there", !!doc.getElementById("apName") && !!doc.getElementById("apGo"));
  check("with the agency's email rule", /must end in @des\.sc\.gov/.test(panel().textContent));
  check("and says nothing is sent from here", /Nothing is sent to them from here/.test(panel().textContent));

  doc.getElementById("apGo").click();
  await settle(100);
  check("empty fields are refused in words", !doc.getElementById("apErr").hidden && sent.length === 0);

  doc.getElementById("apName").value = "Jordan Doe";
  doc.getElementById("apTitle").value = "Deputy Director";
  doc.getElementById("apEmail").value = "jordan.doe@des.sc.gov";
  doc.getElementById("apEmail").dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await settle(400);
  check("Enter adds them", sent.length === 1 && sent[0].email === "jordan.doe@des.sc.gov", JSON.stringify(sent));
  check("they appear on the list", /Jordan Doe/.test(panel().textContent));
  check("and it says how they get in", /sign in with their own work email/.test(doc.getElementById("apSaid").textContent));
  check("focus is back in the form for the next one", doc.activeElement === doc.getElementById("apName"));

  console.log("\nremoving, and making admins");
  const acted = [];
  window.fetch = async (url, opts) => {
    for (const path of ["/api/agency/member/remove", "/api/agency/role"]) {
      if (String(url).includes(path)) {
        acted.push([path, JSON.parse(opts.body).email]);
        const promoted = path.endsWith("/role");
        return { ok: true, status: 200, json: async () => ({ ok: true, is_admin: true, me: "brett.butz@des.sc.gov",
          admin_names: promoted ? ["Brett Butz", "lokesh dandu"] : ["Brett Butz"],
          domain: "des.sc.gov", people: promoted ? people.map((p) => ({ ...p, role: "Admin" })) : people.slice(0, 1),
          says: promoted ? "lokesh dandu is an admin now."
                         : "lokesh dandu is off the organization and signed out." }) };
      }
    }
    return real(url, opts);
  };
  host.innerHTML = "";
  host.appendChild(window.peoplePanel({ ok: true, is_admin: true, me: "brett.butz@des.sc.gov", domain: "des.sc.gov", admin_names: ["Brett Butz"], people },
    "South Carolina Department of Environmental Services"));
  const ownRow = panel().querySelector("tbody tr");
  check("your own row offers nothing", /You/.test(ownRow.textContent)
    && !ownRow.querySelector("[data-remove], [data-role]"));
  const remove = panel().querySelector("[data-remove]");
  check("every other row offers Remove and Make admin", !!remove
    && /Make admin/.test((panel().querySelector("[data-role]") || {}).textContent || ""));
  remove.click();
  await settle(100);
  check("removing asks first", /Remove lokesh dandu\?/.test((doc.getElementById("confirmVeil") || {}).textContent || ""));
  check("and nothing is sent before the answer", acted.length === 0);
  doc.getElementById("confirmYes").click();
  await settle(400);
  check("then it is sent", acted.length === 1 && acted[0][1] === "lokesh.dandu@des.sc.gov");
  check("and the list and the note update", !/lokesh/.test(panel().querySelector("tbody").textContent)
    && /signed out/.test(doc.getElementById("peopleSaid").textContent));

  host.innerHTML = "";
  host.appendChild(window.peoplePanel({ ok: true, is_admin: true, me: "brett.butz@des.sc.gov", domain: "des.sc.gov", admin_names: ["Brett Butz"], people },
    "South Carolina Department of Environmental Services"));
  panel().querySelector("[data-role]").click();
  await settle(100);
  check("making an admin asks first, and says what it allows",
    /Make lokesh dandu an admin\?/.test((doc.getElementById("confirmVeil") || {}).textContent || "")
    && /including you/.test((doc.getElementById("confirmVeil") || {}).textContent || ""));
  doc.getElementById("confirmYes").click();
  await settle(400);
  check("then they are an admin, with Make member offered", /is an admin now/.test(doc.getElementById("peopleSaid").textContent)
    && /Make member/.test(panel().querySelector("[data-role]").textContent));
  check("the add form lets you choose the role", !!doc.getElementById("apRole")
    && doc.querySelector('label[for="apRole"]'));
  window.fetch = real;

  console.log("\na member");
  host.innerHTML = "";
  host.appendChild(window.peoplePanel({ ok: true, is_admin: false, admin_names: ["Brett Butz"],
    people: people.map(({ email, ...p }) => p) }, "South Carolina Department of Environmental Services"));
  check("sees who is in it", /Brett Butz/.test(panel().textContent) && /Admin/.test(panel().textContent));
  check("but no addresses", !/@des\.sc\.gov/.test(panel().textContent));
  check("and no form", !doc.getElementById("apName"));
  check("and is told who can add people", /Brett Butz can add people/.test(panel().textContent));
  host.innerHTML = "";
  host.appendChild(window.peoplePanel({ ok: true, is_admin: false, admin_names: [], needs_admin: true,
    people: people.slice(1).map(({ email, ...p }) => p) }, "South Carolina Department of Environmental Services"));
  check("with no admin yet, it says the GAIUS team appoints one", /no admin yet/.test(panel().textContent)
    && /GAIUS team appoints one/.test(panel().textContent));

  console.log("\npicked one agency, signed in to another");
  host.innerHTML = "";
  host.appendChild(window.peoplePanel({ ok: true, is_admin: false, admin_names: ["lokesh dandu"],
    organization: "DEMO agency — Innovative Infrastructure Advising", people: [] },
    "South Carolina Department of Environmental Services"));
  check("the heading names the organization the people belong to",
    /People in DEMO agency/.test(panel().textContent) && !/Environmental Services/.test(panel().querySelector("h2").textContent));
  window.SCDES_AGENCY = { agency_id: "sc.des", agency: "South Carolina Department of Environmental Services" };
  window.orgMismatch({ organization: { code: "iia.test", label: "DEMO agency — Innovative Infrastructure Advising" } });
  const banner = doc.getElementById("orgMismatch");
  check("a banner says which organization you are really in",
    !!banner && /You are in DEMO agency/.test(banner.textContent) && /not South Carolina Department of Environmental Services/.test(banner.textContent));
  check("it is announced", banner && banner.getAttribute("role") === "status");
  check("and the header names the real organization", /DEMO agency/.test(doc.getElementById("agencyCrumb")?.textContent || ""));
  window.orgMismatch({ organization: { code: "sc.des", label: "South Carolina Department of Environmental Services" } });
  check("no banner when they match", !doc.getElementById("orgMismatch"));

  let signinBody = null;
  const before = window.fetch;
  window.fetch = async (url, opts) => {
    if (String(url).includes("/api/agency/signin")) {
      signinBody = JSON.parse(opts.body);
      return { ok: true, status: 200, json: async () => ({ ok: false, wrong_agency: true,
        error: "That address is not registered to South Carolina Department of Environmental Services. Sign in from the agency it was registered with, or use your South Carolina Department of Environmental Services email." }) };
    }
    return before(url, opts);
  };
  // Pick SCDES the way a person does — the map, the search box, Enter — so
  // the launcher's own record of the choice is what is sent.
  window.showMap();
  await settle(300);
  const sc = doc.querySelector('.st[data-code="SC"]');
  if (sc) sc.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await settle(400);
  const pick = doc.getElementById("agencyPick");
  pick.focus(); pick.value = "Department of Environmental Services";
  pick.dispatchEvent(new window.Event("input", { bubbles: true }));
  await settle(250);
  pick.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await settle(250);
  window.showReturning({ agency: "sc.des", state: "SC" }, "lokesh@iiac.ai");
  await settle(200);
  doc.getElementById("siGo").click();
  await settle(400);
  check("signing in sends the agency you picked", signinBody && signinBody.agency === "sc.des", JSON.stringify(signinBody));
  check("and a wrong one is refused in words", /not registered to South Carolina/.test(doc.getElementById("siError").textContent));
  window.fetch = before;
  if (window.closeLauncher) window.closeLauncher();
  host.innerHTML = "";
  host.appendChild(window.peoplePanel({ ok: true, is_admin: true, me: "brett.butz@des.sc.gov", admin_names: ["Brett Butz"],
    domain: "des.sc.gov", people }, "South Carolina Department of Environmental Services"));

  const unnamed = [...panel().querySelectorAll("input, button, select")].filter((c) =>
    !(c.id && doc.querySelector(`label[for="${c.id}"]`)) && !(c.tagName === "BUTTON" && c.textContent.trim()));
  check("every control has a name", unnamed.length === 0);
  finish(errors, "admins add colleagues and make admins; members see who is in it");
}

main().catch((e) => { console.error(e); process.exit(1); });
