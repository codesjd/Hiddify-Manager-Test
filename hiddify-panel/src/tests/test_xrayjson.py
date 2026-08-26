def test_xrayjson_xtls_security():
    from hiddifypanel.hutils.proxy import xrayjson
    from hiddifypanel.models.proxy import ProxyProto, ProxyL3

    ss = {}
    proxy = {
        'mode': 'direct', 'l3': ProxyL3.tls, 'proto': ProxyProto.vless,
        'security': 'xtls',                     # the field your fix now reads
        'sni': 'test.hiddify.com', 'fingerprint': 'chrome',
        'alpn': 'h2,http/1.1', 'allow_insecure': False,
    }
    xrayjson._add_security(ss, proxy, proxy)

    assert ss['security'] == 'xtls'
    assert ss['tlsSettings']['serverName'] == 'test.hiddify.com'
