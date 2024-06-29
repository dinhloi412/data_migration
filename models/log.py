from odoo import models, fields, api

from .const import created_status, successful_status, failed_status


class ImportLog(models.Model):
    _name = 'import.log'
    _description = "Import log"

    message = fields.Char(string='Message')
    status = fields.Selection([
        (created_status, "Created"), (successful_status, "Successful"), (failed_status, "Failed")
    ], default="created", string="Status")

    type = fields.Char(string='Type')
    data_migration_id = fields.Many2one("data.migration", string="data migration")



