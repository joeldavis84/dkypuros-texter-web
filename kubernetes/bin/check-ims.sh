#!/usr/bin/env bash

set -uo pipefail

imsInterface="${imsInterface:-}"
sipServer="${sipServer:-192.168.27.57}"
sipPort="${sipPort:-5060}"
sipIdentity="${sipIdentity:-user1}"
sipDomain="${sipDomain:-dkypuros}"

info() {
  printf '[check-ims] %s\n' "$*"
}

error() {
  printf '[check-ims] ERROR: %s\n' "$*" >&2
}

## IMS health checking is optional.
if [[ -z "${imsInterface}" ]]; then
  info "imsInterface is unset; IMS health check disabled"
  exit 0
fi

info "checking IMS connectivity"
info "interface=${imsInterface}"
info "SIP server=${sipServer}:${sipPort}"
info "SIP identity=${sipIdentity}@${sipDomain}"

## Confirm the configured interface exists and retrieve its IPv4 address.
if ! imsAddressInfo="$(ip -j -4 addr show dev "${imsInterface}" 2>&1)"; then
  error "unable to inspect interface ${imsInterface}"
  error "${imsAddressInfo}"
  exit 1
fi

imsIp="$(
  printf '%s\n' "${imsAddressInfo}" |
    jq -r '
      first(
        .[0].addr_info[]?
        | select(.family == "inet")
        | .local
      ) // empty
    '
)"

if [[ -z "${imsIp}" ]]; then
  error "interface ${imsInterface} has no IPv4 address"
  exit 1
fi

info "IMS address=${imsIp}"

requestId="${RANDOM}-$$"
callId="health-${requestId}@${sipIdentity}"
branch="z9hG4bK-health-${requestId}"

info "sending SIP OPTIONS to ${sipServer}:${sipPort}"

response="$(
  {
    printf \
      'OPTIONS sip:%s SIP/2.0\r\nVia: SIP/2.0/UDP %s;branch=%s;rport\r\nFrom: <sip:%s@%s>;tag=health\r\nTo: <sip:%s>\r\nCall-ID: %s\r\nCSeq: 1 OPTIONS\r\nMax-Forwards: 70\r\nContent-Length: 0\r\n\r\n' \
      "${sipDomain}" \
      "${imsIp}" \
      "${branch}" \
      "${sipIdentity}" \
      "${sipDomain}" \
      "${sipDomain}" \
      "${callId}"

    sleep 1
  } |
    nc \
      -u \
      -s "${imsIp}" \
      --idle-timeout 2s \
      "${sipServer}" \
      "${sipPort}" \
      2>&1
)"

if grep -q '^SIP/2.0 200' <<< "${response}"; then
  statusLine="$(grep -m1 '^SIP/2.0' <<< "${response}")"
  info "IMS health check succeeded: ${statusLine}"
  exit 0
fi

error "IMS health check failed"

if [[ -z "${response}" ]]; then
  error "no response received from ${sipServer}:${sipPort}"
else
  error "response was:"
  printf '%s\n' "${response}" >&2
fi

exit 1
