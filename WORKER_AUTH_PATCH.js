/*
PROPERTY INVESTMENT DIGEST — SERVER-SIDE AUTH PATCH FOR EXISTING ATTOM WORKER

Purpose:
- Require a valid Firebase email/password session token before protected ATTOM routes return data.
- Restrict access to an explicit email allow-list.
- Restrict browser CORS to the Property Investment Digest GitHub Pages origin.

IMPORTANT:
This file is a PATCH/HELPER for the EXISTING ATTOM Worker. It is not a replacement for
your current ATTOM property-search logic because the current Worker source was not available
in the website files. Merge these helpers into the existing Worker, then call
requireAuthorizedUser() before each protected property-data route.

Required Worker environment settings:
  FIREBASE_WEB_API_KEY = the Firebase web API key used by the site
  AUTHORIZED_EMAILS = comma-separated authorized emails
  ALLOWED_ORIGIN = https://tonyhernandezusa-code.github.io

Never put the ATTOM API secret into GitHub Pages HTML/JavaScript.
*/

function corsHeaders(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "https://tonyhernandezusa-code.github.io",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Authorization,Content-Type,Accept",
    "Access-Control-Allow-Credentials": "false",
    "Vary": "Origin"
  };
}

function jsonResponse(body, status, env) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: Object.assign({"Content-Type":"application/json; charset=utf-8"}, corsHeaders(env))
  });
}

function normalizeAllowedEmails(raw) {
  return String(raw || "")
    .split(",")
    .map(function(x){ return x.trim().toLowerCase(); })
    .filter(Boolean);
}

async function requireAuthorizedUser(request, env) {
  var authHeader = request.headers.get("Authorization") || "";
  if (!authHeader.startsWith("Bearer ")) {
    return {ok:false, response:jsonResponse({error:"Authentication required."}, 401, env)};
  }

  var idToken = authHeader.slice(7).trim();
  if (!idToken) {
    return {ok:false, response:jsonResponse({error:"Authentication required."}, 401, env)};
  }

  if (!env.FIREBASE_WEB_API_KEY) {
    return {ok:false, response:jsonResponse({error:"Server authentication is not configured."}, 500, env)};
  }

  // Firebase Identity Toolkit validates the supplied Firebase ID token and returns
  // the account associated with that token.
  var verifyResponse = await fetch(
    "https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=" +
      encodeURIComponent(env.FIREBASE_WEB_API_KEY),
    {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({idToken:idToken})
    }
  );

  if (!verifyResponse.ok) {
    return {ok:false, response:jsonResponse({error:"Your sign-in session is invalid or expired."}, 401, env)};
  }

  var verifyData = await verifyResponse.json();
  var user = verifyData.users && verifyData.users[0];
  var email = user && String(user.email || "").toLowerCase();

  if (!email) {
    return {ok:false, response:jsonResponse({error:"No authorized email was found for this account."}, 403, env)};
  }

  var allowed = normalizeAllowedEmails(env.AUTHORIZED_EMAILS);
  if (!allowed.includes(email)) {
    return {ok:false, response:jsonResponse({error:"This account is not authorized for Professional Property Search."}, 403, env)};
  }

  return {ok:true, user:{email:email, localId:user.localId || ""}};
}

/*
MERGE EXAMPLE inside your existing Worker fetch handler:

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, {status:204, headers:corsHeaders(env)});
    }

    const url = new URL(request.url);

    // Protect EVERY route that can return licensed property data.
    const protectedPaths = [
      "/property-search",
      "/neighborhood-data",
      "/foreclosure-search"
      // Add any other ATTOM / property-data routes used by this Worker.
    ];

    if (protectedPaths.includes(url.pathname)) {
      const auth = await requireAuthorizedUser(request, env);
      if (!auth.ok) return auth.response;
    }

    // KEEP THE REST OF YOUR EXISTING ROUTE / ATTOM CODE HERE.
  }
};

SECURITY TEST after deployment:
1. Open this directly in an incognito browser:
   https://attom-proxy.tonyhernandezusa.workers.dev/property-search?address=...
2. Without an Authorization header, it MUST return HTTP 401.
3. If it still returns property data, the Worker is NOT protected yet.
*/
