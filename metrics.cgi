#!/bin/sh
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Jakub Jirutka <jakub@jirutka.cz>
# Website: https://github.com/jirutka/keepalived-exporter-cgi/
# Version: 0.0.0
# Requirements: jq, keepalived-dump-json
#
# A CGI script to expose keepalived statistics as Prometheus-style metrics.
#
# The metrics are the same as produced by
# https://github.com/mehdy/keepalived-exporter.
set -u

# keepalived is usually installed in /usr/sbin, but some CGI servers (thttpd)
# exports PATH without /sbin directories.
export PATH="$PATH:/usr/sbin"

# Path to the helper script that will be run as root via doas or sudo.
readonly KEEPALIVED_DUMP_JSON='/usr/local/bin/keepalived-dump-json'

readonly JQ_SCRIPT='
def format_labels($o):
	"{" + (
		$o
		| to_entries
		| map("\(.key)=\"\(.value)\"")
		| join(",")
	) + "}";

def parse_vip($s):
	($s | tostring | split(" ") | map(select(length > 0))) as $t
	| if ($t | length) >= 3
		then {ip_address: $t[0], intf: $t[2]}
		else null
	end;

def emit($name; $labels; $val):
	if $labels == null or ($labels | length) == 0
	then "\($name) \($val)"
	else "\($name)\(format_labels($labels)) \($val)"
	end;

emit("keepalived_up"; {}; 1),

.[] as $vrrp
| ($vrrp.data // {}) as $d
| ($vrrp.stats // {}) as $s
| ($d.iname // "") as $iname
| ($d.vrid // "") as $vrid
| ($d.ifp_ifname // "") as $ifp
| ($d.state // 0) as $state

| (
	($d.vips // []) as $vips
	| if ($vips | length) > 0
		then
			$vips[]
			| parse_vip(.)
			| select(. != null)
			| emit("keepalived_vrrp_state";
				{iname:$iname, intf:.intf, vrid:$vrid, ip_address:.ip_address};
				$state)
		else
			emit("keepalived_vrrp_state";
				{iname:$iname, intf:$ifp, vrid:$vrid, ip_address:""};
				$state)
	end
),

(
	($d.evips // [])[]
	| parse_vip(.)
	| select(. != null)
	| emit("keepalived_vrrp_excluded_state";
		{iname:$iname, intf:.intf, vrid:$vrid, ip_address:.ip_address};
		$state)
),

emit("keepalived_address_list_errors_total";     {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.addr_list_err // 0)),
emit("keepalived_advertisements_interval_errors_total"; {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.advert_interval_err // 0)),
emit("keepalived_advertisements_received_total"; {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.advert_rcvd // 0)),
emit("keepalived_advertisements_sent_total";     {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.advert_sent // 0)),
emit("keepalived_authentication_failure_total";  {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.auth_failure // 0)),
emit("keepalived_authentication_invalid_total";  {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.invalid_authtype // 0)),
emit("keepalived_authentication_mismatch_total"; {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.authtype_mismatch // 0)),
emit("keepalived_become_master_total";           {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.become_master // 0)),
emit("keepalived_gratuitous_arp_delay_total";    {iname:$iname, intf:$ifp, vrid:$vrid}; ($d.garp_delay // 0)),
emit("keepalived_invalid_type_received_total";   {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.invalid_type_rcvd // 0)),
emit("keepalived_ip_ttl_errors_total";           {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.ip_ttl_err // 0)),
emit("keepalived_packet_length_errors_total";    {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.packet_len_err // 0)),
emit("keepalived_priority_zero_received_total";  {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.pri_zero_rcvd // 0)),
emit("keepalived_priority_zero_sent_total";      {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.pri_zero_sent // 0)),
emit("keepalived_release_master_total";          {iname:$iname, intf:$ifp, vrid:$vrid}; ($s.release_master // 0))
'

# Metric headers (HELP/TYPE). Keep these in the same order as output for readability.
readonly METADATA="\
# HELP keepalived_up Whether keepalived is running and the last JSON dump was successfully refreshed (1 for yes, 0 for no).
# TYPE keepalived_up gauge
# HELP keepalived_vrrp_state State of vrrp
# TYPE keepalived_vrrp_state gauge
# HELP keepalived_vrrp_excluded_state VRRP instance state for excluded VIPs.
# TYPE keepalived_vrrp_excluded_state gauge
# HELP keepalived_address_list_errors_total Number of VRRP address list errors.
# TYPE keepalived_address_list_errors_total counter
# HELP keepalived_advertisements_interval_errors_total Number of VRRP advertisement interval errors.
# TYPE keepalived_advertisements_interval_errors_total counter
# HELP keepalived_advertisements_received_total Number of VRRP advertisements received.
# TYPE keepalived_advertisements_received_total counter
# HELP keepalived_advertisements_sent_total Number of VRRP advertisements sent.
# TYPE keepalived_advertisements_sent_total counter
# HELP keepalived_authentication_failure_total Number of VRRP authentication failures.
# TYPE keepalived_authentication_failure_total counter
# HELP keepalived_authentication_invalid_total Number of VRRP packets received with invalid authentication type.
# TYPE keepalived_authentication_invalid_total counter
# HELP keepalived_authentication_mismatch_total Number of VRRP packets received with authentication type mismatch.
# TYPE keepalived_authentication_mismatch_total counter
# HELP keepalived_become_master_total Number of times the instance became MASTER.
# TYPE keepalived_become_master_total counter
# HELP keepalived_gratuitous_arp_delay_total Gratuitous ARP delay.
# TYPE keepalived_gratuitous_arp_delay_total counter
# HELP keepalived_invalid_type_received_total Number of VRRP packets with invalid type received.
# TYPE keepalived_invalid_type_received_total counter
# HELP keepalived_ip_ttl_errors_total Number of VRRP IP TTL errors.
# TYPE keepalived_ip_ttl_errors_total counter
# HELP keepalived_packet_length_errors_total Number of VRRP packet length errors.
# TYPE keepalived_packet_length_errors_total counter
# HELP keepalived_priority_zero_received_total Number of VRRP packets received with priority 0.
# TYPE keepalived_priority_zero_received_total counter
# HELP keepalived_priority_zero_sent_total Number of VRRP packets sent with priority 0.
# TYPE keepalived_priority_zero_sent_total counter
# HELP keepalived_release_master_total Number of times the instance released MASTER state.
# TYPE keepalived_release_master_total counter

"

run_as_root() {
	if command -v doas >/dev/null; then
		doas -nu root -- "$@"
	else
		sudo -nu root -- "$@"
	fi
}

status_text() {
	case "$1" in
		200) echo 'OK';;
		405) echo 'Method Not Allowed';;
		500) echo 'Internal Server Error';;
	esac
}

finish() {
	local status="$1"
	local msg="$2"

	if [ "${GATEWAY_INTERFACE-}" ]; then
		echo "Status: $status $(status_text "$status")"
		echo 'Content-Type: text/plain'
		echo ''
		printf '%s\n' "$msg"
		exit 0
	elif [ "$status" = 200 ]; then
		printf '%s\n' "$msg"
		exit 0
	else
		printf '%s\n' "$msg" >&2
		exit 1
	fi
}


[ "${REQUEST_METHOD:-}" ] && [ "$REQUEST_METHOD" != 'GET' ] \
	&& finish 405 'Only GET method is supported'

command -v keepalived >/dev/null \
	|| finish 500 'keepalived not found'

[ -e "$KEEPALIVED_DUMP_JSON" ] \
	|| finish 500 "$KEEPALIVED_DUMP_JSON doesn't exist"

keepalived --signum=JSON >/dev/null 2>&1 \
	|| finish 500 'keepalived is not built with JSON support'

out="$(run_as_root "$KEEPALIVED_DUMP_JSON")"
case "$?" in
	0) ;;
	10 | 11) finish 200 'keepalived_up 0' ;;
	*) finish 500 "${out:-"Unknown error"}" ;;
esac

if metrics="$(printf '%s\n' "$out" | jq -r "$JQ_SCRIPT")"; then
	finish 200 "$METADATA$metrics"
else
	finish 500 "Failed to parse or process $JSON_FILE"
fi
