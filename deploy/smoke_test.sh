#!/usr/bin/env bash
# Usage: deploy/smoke_test.sh https://shop.example.com [admin-path/]
# Checks a live site from the outside. Prints PASS/FAIL lines; exits 1 if anything fails.
set -u
BASE="${1:?usage: smoke_test.sh https://domain [admin-path/]}"
ADMIN="${2:-admin/}"
HOST="${BASE#https://}"
fail=0

check() { if [ "$2" = "$3" ]; then echo "PASS  $1"; else echo "FAIL  $1 (expected $2, got $3)"; fail=1; fi; }
code()  { curl -s -o /dev/null -w "%{http_code}" "$@"; }

check "home page loads"                     200 "$(code "$BASE/")"
check "http redirects to https"             301 "$(code "http://$HOST/")"
check "health check"                        200 "$(code "$BASE/healthz/")"
check "static files are served"             200 "$(code "$BASE/static/css/style.css")"
check "staff area needs a login"            302 "$(code "$BASE/staff/")"
check "callback with a wrong token is 404"  404 "$(code -X POST -d '{}' "$BASE/payments/callback/WRONG/")"
check "unknown page is 404"                 404 "$(code "$BASE/no-such-page/")"
check ".env is not served"                  404 "$(code "$BASE/.env")"
check ".git is not served"                  404 "$(code "$BASE/.git/HEAD")"
check "admin login page exists"             200 "$(code "$BASE/${ADMIN}login/")"
if [ "$ADMIN" != "admin/" ]; then
  check "default /admin/ path is hidden"    404 "$(code "$BASE/admin/")"
fi

if curl -s "$BASE/no-such-page/" | grep -q "could not find that page"; then
  echo "PASS  DEBUG is off (friendly 404 page)"; else echo "FAIL  the 404 page is not ours: is DEBUG on?"; fail=1; fi

headers=$(curl -sI "$BASE/")
for h in strict-transport-security x-frame-options x-content-type-options referrer-policy permissions-policy; do
  if echo "$headers" | grep -qi "^$h:"; then echo "PASS  header $h"; else echo "FAIL  header $h is missing"; fail=1; fi
done
if echo "$headers" | grep -qiE "^(content-security-policy|content-security-policy-report-only):"; then
  echo "PASS  header content-security-policy"; else echo "FAIL  no content security policy"; fail=1; fi
if echo "$headers" | grep -qiE "^server:.*[0-9]"; then echo "FAIL  the Server header reveals a version"; fail=1; else echo "PASS  server version hidden"; fi

end=$(echo | openssl s_client -servername "$HOST" -connect "$HOST:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
if [ -n "$end" ]; then
  left=$(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 ))
  if [ "$left" -ge 20 ]; then echo "PASS  certificate valid for $left more days"; else echo "FAIL  certificate expires in $left days"; fail=1; fi
else
  echo "FAIL  could not read the certificate"; fail=1
fi

[ "$fail" -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit "$fail"