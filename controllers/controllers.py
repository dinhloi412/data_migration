# -*- coding: utf-8 -*-
# from odoo import http


# class DataMigration(http.Controller):
#     @http.route('/data_migration/data_migration', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/data_migration/data_migration/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('data_migration.listing', {
#             'root': '/data_migration/data_migration',
#             'objects': http.request.env['data_migration.data_migration'].search([]),
#         })

#     @http.route('/data_migration/data_migration/objects/<model("data_migration.data_migration"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('data_migration.object', {
#             'object': obj
#         })
