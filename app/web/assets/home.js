/* The home page — the public front door of GoverningAI.US.

   Brett, Oct 2026: "someone goes to governingai.us. It's a standard webpage.
   Then there would be a 'Begin' or 'start' button which would take them to the
   app page, which is where they would … click on your state/agency. There
   would also be a 'Login' button at the top right for anyone who is already
   registered."

   Shown to anybody who is not signed in (launcher.js decides). Begin opens the
   map; Log in opens the log-in card. Nothing here reads or writes anything —
   it is a page of words and two doors.

   The wording follows the product's rules: American English, and the words
   on the banned list are not used (the old site's "deploy AI on your terms"
   reads "adopt AI on your terms" here). */

const HOME = { wired: false };

function homeMarkup() {
  return `
    <header class="home-top">
      <div class="home-wrap home-bar">
        <a class="home-brand" href="/" aria-label="GoverningAI.US home">
          <span class="gaius-logo gaius-logo-word" aria-hidden="true"></span></a>
        <button type="button" class="home-login" id="homeLogin">Log in</button>
      </div>
    </header>

    <main id="homeMain">
      <section class="home-hero" aria-labelledby="homeH1">
        <div class="home-wrap home-hero-grid">
          <div>
            <p class="home-eyebrow">Innovative Infrastructure Advising · GoverningAI.US</p>
            <h1 id="homeH1">Adopt AI on your terms, with your team.</h1>
            <p class="home-lede">GoverningAI.US helps a public organization write its own AI rules in
              plain language, then use AI safely by those rules — from the first idea to the day
              a tool is switched off.</p>
            <div class="home-cta">
              <button type="button" class="home-begin" id="homeBegin">Begin</button>
              <span class="home-or">Already registered? <button type="button" class="home-link"
                id="homeLogin2">Log in</button></span>
            </div>
          </div>
          <aside class="home-start" aria-labelledby="homeHowH">
            <h2 id="homeHowH">How to start</h2>
            <ol class="home-steps">
              <li><b>Choose your state and agency.</b> Not on the list? Choose Other.</li>
              <li><b>Register and accept the Terms of Use.</b> Your name, title, work email and
                governmental unit.</li>
              <li><b>Verify your work email.</b> A six-digit code is sent to it, and you are in.</li>
            </ol>
          </aside>
        </div>
      </section>

      <section class="home-sec" aria-labelledby="homeWhyH">
        <div class="home-wrap">
          <h2 id="homeWhyH">What you get</h2>
          <div class="home-cards">
            <article class="home-card"><h3>Your framework, free</h3>
              <p>Answer plain-language questions and get your own AI governance framework,
                ready for whoever holds the authority to adopt it. Free for governmental units,
                and yours to keep, publish and share.</p></article>
            <article class="home-card"><h3>Your data stays yours</h3>
              <p>Everything you enter belongs to your organization and stays in your own
                account. It is not sold, and it is never pooled with any other organization's.</p></article>
            <article class="home-card"><h3>Built for public bodies</h3>
              <p>State and federal agencies, counties, cities, school districts, special districts,
                tribal governments and regional councils — each with its own space.</p></article>
          </div>
        </div>
      </section>

      <section class="home-sec" aria-labelledby="homeReadyH">
        <div class="home-wrap home-ready">
          <h2 id="homeReadyH">Ready when you are</h2>
          <p>Registering takes a few minutes. Your framework is free and stays yours.</p>
          <p><button type="button" class="home-begin" id="homeBegin2">Begin</button></p>
        </div>
      </section>
    </main>

    <footer class="home-foot">
      <div class="home-wrap">
        <p>Innovative Infrastructure Advising, LLC · iiac.ai · Charleston, SC</p>
        <p><a href="/assets/legal/GoverningAI_Terms_of_Use_and_License_v1.0.docx" download>Terms of Use
          and License Agreement</a></p>
      </div>
    </footer>`;
}

function showHome() {
  const host = document.getElementById("home");
  if (!host) return false;
  if (!HOME.wired) {
    host.innerHTML = homeMarkup();
    HOME.wired = true;
    const begin = () => { hideHome(); if (window.openLauncher) window.openLauncher(); };
    const login = () => { hideHome(); if (window.showLogin) window.showLogin(); };
    ["homeBegin", "homeBegin2"].forEach((id) => { document.getElementById(id).onclick = begin; });
    ["homeLogin", "homeLogin2"].forEach((id) => { document.getElementById(id).onclick = login; });
  }
  host.hidden = false;
  document.body.classList.add("home-open");
  const h1 = document.getElementById("homeH1");
  if (h1) { h1.setAttribute("tabindex", "-1"); h1.focus(); }
  return true;
}

function hideHome() {
  const host = document.getElementById("home");
  if (host) host.hidden = true;
  document.body.classList.remove("home-open");
}

window.showHome = showHome;
window.hideHome = hideHome;
