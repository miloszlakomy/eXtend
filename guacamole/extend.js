window.eXtend = (function() {
    'use strict';

    var eXtend = function(port) {
        var extend = this;

        $(function() {
            extend.$status = $('#extend-status');
            extend.$id = $('#extend-id-container');
            extend.$guac = $('#extend-guacamole');

            extend.statusMsg('document loaded');

            $('body').click(function() {
                var elem = document.getElementById('extend-container');
                var req = elem.requestFullScreen
                      || elem.webkitRequestFullScreen
                      || elem.mozRequestFullScreen;
                req.call(elem);
            });

            extend.connect(port);
        });
    };

    var getArgs = function(href) {
        var args = {};
        var search = document.location.search;

        if (href !== undefined) {
            search = href.substr(href.indexOf('?'));
        }

        search.replace(/\??(?:([^=]+)=([^&]*)&?)/g, function () {
            function decode(s) {
                return decodeURIComponent(s.split("+").join(" "));
            }

            args[decode(arguments[1])] = decode(arguments[2]);
        });

        return args;
    }

    eXtend.prototype = {
        statusMsg: function(msg) {
            this.$status.html(this.$status.html() + '<br/>' + msg);
        },

        loginToGuacamole: function(url, login, pass) {
            var extend = this;
            var data = {
                'username': login,
                'password': pass
            };

            $.post(url, data, function() {
                extend.statusMsg('login successful');
            }, function(evt) {
                extend.statusMsg('login error: ' + evt);
            });
        },

        startGuacamole: function(url) {
            var extend = this;
            var args = getArgs();

            if (!('id' in args)) {
                $.extend(args, getArgs(url));
                args['extend_id'] = extend.$id.text();
                extend.statusMsg('args: ' + $.param(args));
                window.location.search = $.param(args);
            }

            $.get(url, function(xml) {
                var $xml = $(xml);
                var $scripts = [];
                var $styles = [];

                extend.statusMsg('appending guacamole');
                $xml.find('head').children().each(function() {
                    var $this = $(this);
                    if ($this.is('link')
                            && $this.attr('rel') === 'stylesheet') {
                        $('head').append(this);
                    }
                });
                $xml.find('body').children().each(function() {
                    var $this = $(this);
                    if ($this.is('script')) {
                        $scripts.push($this);
                    } else {
                        $(this).addClass('extend-guacamole-node');
                        $('body').append(this);
                    }
                });

                extend.processScriptNodes($scripts, 0);
            });
        },

        processScriptNodes: function($scripts, startIndex) {
            var extend = this;

            for (var i = startIndex; i < $scripts.length; ++i) {
                extend.statusMsg('processing script ' + i + '/' + $scripts.length);

                var $extend = $scripts[i];
                var srcUrl = $extend.attr('src');

                if (srcUrl !== undefined) {
                    extend.statusMsg('executing script: ' + srcUrl);
                    $.getScript(srcUrl, function() {
                        extend.processScriptNodes($scripts, i + 1);
                    });
                    return;
                }

                var code = $extend.html();
                if (code) {
                    extend.statusMsg('executing inline javascript');
                    $.globalEval(code);
                }
            }

            if (window.onload) {
                extend.statusMsg('executing window.onload event');
                window.onload();
            }

            extend.statusMsg('done with scripts');
        },

        stopGuacamole: function() {
            this.$guac.empty();
            this.$id.show();
            this.$status.show();
        },

        connect: function(port) {
            var extend = this;
            this.serverUrl = 'ws://' + document.domain + ':' + port;
            this.statusMsg('connecting to ' + this.serverUrl);

            this.sock = new WebSocket(this.serverUrl);
            this.sock.onopen = function() {
                var w = window.screen.width;
                var h = window.screen.height;
                var args = getArgs();

                extend.statusMsg('args:');
                for (var key in args) {
                    extend.statusMsg('- ' + key + ': ' + args[key]);
                }
                    
                if ('extend_id' in args) {
                    extend.statusMsg('renewing ID: ' + args.extend_id);
                    extend.sock.send('id ' + args.extend_id + '\n');
                } else {
                    extend.statusMsg('waiting for ID')
                    extend.sock.send('get-id\n');
                }

                extend.statusMsg('sending resolution info (' + w + 'x' + h + ')')
                extend.sock.send('resolution ' + w + ' ' + h + '\n')
            }
            this.sock.onclose = function(evt) {
                extend.statusMsg('socket closed, code: ' + evt.code + ', reason: ' + evt.reason);
                extend.stopGuacamole();
                //setTimeout(1000, function() { extend.connect(port) });
            }
            this.sock.onmessage = function(msg) {
                var argv = msg.data.split(' ');
                switch (argv[0]) {
                case 'id':
                    extend.statusMsg('got id: ' + argv[1]);
                    extend.$id.text(argv[1]).show();
                    break;
                case 'login':
                    extend.statusMsg('logging in');
                    extend.loginToGuacamole(argv[1], argv[2], argv[3]);
                    break;
                case 'display':
                    extend.statusMsg('displaying ' + argv[1]);
                    extend.startGuacamole(argv[1]);
                    break;
                default:
                    extend.statusMsg('unknown message: ' + msg);
                    break;
                }
            }
        }
    };

    return new eXtend(4242);
})();
