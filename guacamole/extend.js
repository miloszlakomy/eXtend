window.eXtend = (function() {
    'use strict';

    var statusMsg = function(msg) {
        var $status = $('#extend-status');
        $status.html($status.html() + '<br/>' + msg);
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

    var Guacamole = function() {};

    Guacamole.prototype = {
        login: function(url, login, pass) {
            var data = {
                'username': login,
                'password': pass
            };

            $.post(url, data, function() {
                statusMsg('login successful');
            }, function(evt) {
                statusMsg('login error: ' + evt);
            });
        },

        start: function(id, url) {
            var args = getArgs();

            if (!('id' in args)) {
                $.extend(args, getArgs(url));
                args['extend_id'] = id;
                statusMsg('args: ' + $.param(args));

                window.location.search = $.param(args);
            }

            this._load(url);
            $('#extend-status').hide();
            $('#extend-id-container').hide();
        },

        stop: function() {
            $('.extend-guacamole-node').remove();
            $('#extend-status').show();
        },

        _load: function(url) {
            var guac = this;
            statusMsg('loading ' + url);

            $.get(url, function(xml) {
                var $xml = $(xml);
                var $scripts = [];
                var $styles = [];

                statusMsg('appending guacamole');
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

                try {
                    console.log('start');
                    guac._processScriptNodes($scripts, 0);
                    console.log('done');
                } catch (e) {
                    statusMsg(e);
                    guac.stop();
                }
            });
        },

        _processScriptNodes: function($scripts, startIndex) {
            var guac = this;

            for (var i = startIndex; i < $scripts.length; ++i) {
                statusMsg('processing script ' + i + '/' + $scripts.length);

                var $script = $scripts[i];
                var srcUrl = $script.attr('src');

                if (srcUrl !== undefined) {
                    statusMsg('executing script: ' + srcUrl);
                    $.getScript(srcUrl, function() {
                        guac._processScriptNodes($scripts, i + 1);
                    });
                    return;
                }

                var code = $script.html();
                if (code) {
                    statusMsg('executing inline javascript');
                    $.globalEval(code);
                }
            }

            if (window.onload) {
                statusMsg('executing window.onload event');
                window.onload();
            }

            statusMsg('done with scripts');
        }
    };

    var eXtend = function(port) {
        var extend = this;

        this.guacamole = new Guacamole();

        $(function() {
            statusMsg('document loaded');

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

    eXtend.prototype = {
        _reconnect: function(id) {
            statusMsg('reconnecting, id = ' + id);
            this.sock.send('reconnect ' + id + '\n');
        },

        _init: function() {
            var w = window.screen.width;
            var h = window.screen.height;

            statusMsg('connecting, resolution = ' + w + 'x' + h);
            this.sock.send('connect ' + w + ' ' + h + '\n');
        },

        connect: function(port) {
            var extend = this;

            this.serverUrl = 'ws://' + document.domain + ':' + port;
            statusMsg('connecting to ' + this.serverUrl);

            this.sock = new WebSocket(this.serverUrl);
            this.sock.onopen = function() {
                var args = getArgs();

                statusMsg('args:');
                for (var key in args) {
                    statusMsg('- ' + key + ': ' + args[key]);
                }
                    
                if ('extend_id' in args) {
                    extend._reconnect(args.extend_id);
                } else {
                    extend._init();
                }
            };

            this.sock.onclose = function(evt) {
                statusMsg('socket closed, code: ' + evt.code + ', reason: ' + evt.reason);
                extend.guacamole.stop();
                window.history.pushState(null, 'eXtend web client', '/');
                //setTimeout(1000, function() { extend.connect(port) });
            };

            this.sock.onmessage = function(msg) {
                var argv = msg.data.trim().split(' ');
                switch (argv[0]) {
                case 'display':
                    var args = getArgs();

                    statusMsg('got id: ' + argv[1]);
                    $('#extend-id-container').text(argv[1]).show();

                    statusMsg('displaying ' + argv[2]);
                    extend.guacamole.start(argv[1], argv[2]);
                    break;
                case 'login':
                    statusMsg('logging in');
                    extend.guacamole.login(argv[1], argv[2], argv[3]);
                    break;
                default:
                    statusMsg('unknown message: ' + msg.data);
                    break;
                }
            };
        },
    };

    return new eXtend(4242);
})();

