#!/bin/bash
cd $(dirname -- "$0")
source ./common/utils.sh

echo "================================================================"
echo "                   Hiddify Diagnostic Report                    "
echo "================================================================"

# Get MAIN_DOMAIN and SERVER_IP
MAIN_DOMAIN=$(grep "^MAIN_DOMAIN=" config.env 2>/dev/null | cut -d'=' -f2)
if [[ -z "$MAIN_DOMAIN" ]]; then
    MAIN_DOMAIN=$(hconfig "main_domain" 2>/dev/null)
fi
SERVER_IP=$(curl --connect-timeout 2 -s https://v4.ident.me/ || echo "")

echo "--- 1. DNS & Network ---"
if [[ -n "$MAIN_DOMAIN" && -n "$SERVER_IP" ]]; then
    DOMAIN_IP=$(dig +short -t a "$MAIN_DOMAIN" | tail -n1)
    if [[ "$DOMAIN_IP" == "$SERVER_IP" ]]; then
        success "PASS: MAIN_DOMAIN ($MAIN_DOMAIN) resolves to server IP ($SERVER_IP)"
    elif [[ -z "$DOMAIN_IP" ]]; then
        warning "WARN: MAIN_DOMAIN ($MAIN_DOMAIN) does not resolve to any IP"
    else
        warning "WARN: MAIN_DOMAIN ($MAIN_DOMAIN) resolves to $DOMAIN_IP, expected $SERVER_IP"
    fi
else
    warning "WARN: Could not determine MAIN_DOMAIN or SERVER_IP for check"
fi

if { ss -tln 2>/dev/null || netstat -tln 2>/dev/null; } | grep -q ":80 " && { ss -tln 2>/dev/null || netstat -tln 2>/dev/null; } | grep -q ":443 "; then
    success "PASS: Ports 80 and 443 are locally bound"
else
    error "FAIL: Ports 80 and 443 are not both locally bound (check haproxy/nginx)"
fi

echo "--- 2. Memory & Swap ---"
mem_total_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
swap_total_kb=$(grep SwapTotal /proc/meminfo | awk '{print $2}')
mem_total_mb=$(( mem_total_kb / 1024 ))
swap_total_mb=$(( swap_total_kb / 1024 ))

if [[ $mem_total_mb -lt 450 && $swap_total_mb -eq 0 ]]; then
    warning "WARN: Memory is ${mem_total_mb}MB with 0MB swap (512MB target may OOM)"
else
    success "PASS: Memory is ${mem_total_mb}MB, Swap is ${swap_total_mb}MB"
fi

echo "--- 3. Certificates ---"
cert_found=0
cert_failed=0
for crt in /opt/hiddify-manager/ssl/*.crt; do
    if [[ -f "$crt" ]]; then
        cert_found=1
        end_date=$(openssl x509 -enddate -noout -in "$crt" 2>/dev/null | cut -d= -f2)
        issuer=$(openssl x509 -issuer -noout -in "$crt" 2>/dev/null | cut -d= -f2-)
        
        # Check if expired
        if openssl x509 -checkend 0 -noout -in "$crt" >/dev/null 2>&1; then
            if echo "$issuer" | grep -qi "hiddify"; then
                warning "WARN: Cert $(basename "$crt") is valid but self-signed ($issuer)"
            else
                success "PASS: Cert $(basename "$crt") is valid (expires $end_date)"
            fi
        else
            error "FAIL: Cert $(basename "$crt") is EXPIRED ($end_date)"
            cert_failed=1
        fi
    fi
done
if [[ $cert_found -eq 0 ]]; then
    warning "WARN: No certificates found in /opt/hiddify-manager/ssl/"
fi

echo "--- 4. Core Ports & Services ---"
cores_ok=1
if ! curl -s --connect-timeout 1 http://127.0.0.1:10085/ >/dev/null 2>&1 && ! { ss -tln 2>/dev/null || netstat -tln 2>/dev/null; } | grep -q ":10085"; then
    error "FAIL: Xray control port 10085 not answering"
    cores_ok=0
fi
if ! curl -s --connect-timeout 1 http://127.0.0.1:10086/ >/dev/null 2>&1 && ! { ss -tln 2>/dev/null || netstat -tln 2>/dev/null; } | grep -q ":10086"; then
    error "FAIL: Sing-box control port 10086 not answering"
    cores_ok=0
fi

# 5 core services
for s in hiddify-xray hiddify-singbox hiddify-haproxy hiddify-nginx hiddify-panel; do
    if systemctl is-active --quiet $s; then
        :
    else
        error "FAIL: Service $s is not active"
        cores_ok=0
    fi
done

if [[ $cores_ok -eq 1 ]]; then
    success "PASS: Core ports (10085, 10086) and 5 core services are active"
fi

echo "--- 5. JSON Configuration ---"
if [[ -f "current.json" ]]; then
    if jq empty current.json 2>/dev/null; then
        success "PASS: current.json is valid JSON"
    else
        error "FAIL: current.json is corrupted or invalid JSON"
    fi
else
    warning "WARN: current.json not found"
fi

echo "================================================================"
