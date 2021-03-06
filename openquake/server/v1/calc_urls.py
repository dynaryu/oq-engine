from django.conf.urls import patterns, url

# each url is prefixed with /v1/calc/
urlpatterns = patterns(
    'openquake.server.views',
    url(r'^list$', 'calc'),
    url(r'^(\d+)$', 'calc_info'),
    url(r'^(\d+)/status$', 'calc'),
    url(r'^(\d+)/results$', 'calc_results'),
    url(r'^(\d+)/traceback$', 'get_traceback'),
    url(r'^(\d+)/log/size$', 'get_log_size'),
    url(r'^(\d+)/log/(\d*):(\d*)$', 'get_log_slice'),
    url(r'^(\d+)/remove$', 'calc_remove'),
    url(r'^result/(\d+)$', 'get_result'),
    url(r'^run$', 'run_calc'),

    url(r'^(\d+)/result/list$', 'calc_results'),
    url(r'^\d+/result/(\d+)$', 'get_result'),
)
