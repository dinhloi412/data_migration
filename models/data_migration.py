import base64
import io
from typing import Union

import requests
import csv
import pandas as pd
import csv
from odoo import models, fields, api
from odoo.exceptions import UserError

from . import const


class DataMigration(models.Model):
    _name = 'data.migration'
    _description = 'Data Migration'
    _inherit = "mail.thread"

    name = fields.Char(string="Name", required=True)
    schemas = fields.Selection(
        lambda self: self._get_schemas(),
        string="Schemas",
        required=True
    )
    type = fields.Selection([("file_import", "File"), ("url_import", "Url")], default="file_import",
                            string="Import type", required=True)
    tables = fields.Char(string="Tables", required=True)
    file_import = fields.Binary(string="File")
    file_name = fields.Char(string="File Name")
    url_import = fields.Text(string="Url")
    verify = fields.Boolean(string="Verify", default=False)
    categories = fields.Selection([("create", "Create"), ("update", "Update")], string="Categories",
                                  default="create", required=True)
    log_ids = fields.One2many("import.log", "data_migration_id", string="Logs")

    @api.model
    def create(self, vals):
        try:
            table = self._get_table(vals["schemas"], vals["tables"])
            if not table:
                raise UserError("can not get table")
            # if vals["type"] == "url_import":
            #     atts_data = requests.get(vals["url_import"])
            #     vals["file_import"] = atts_data.content
            return super(DataMigration, self).create(vals)
        except Exception as e:
            raise UserError(e)

    def write(self, vals):
        try:
            if vals.get("schemas") and vals.get("tables"):
                table = self._get_table(vals["schemas"], vals["tables"])
                if not table:
                    raise UserError("can not get table")
            # if vals.get("url_import"):
                # atts_data = requests.get(vals["url_import"])
                # vals["file_import"] = base64.b64encode(atts_data.content)
                vals["verify"] = False                       
            return super(DataMigration, self).write(vals)
        except Exception as e:
            raise UserError(e)

    def _get_schemas(self):
        query = """select schema_name from information_schema.schemata"""
        self.env.cr.execute(query)
        res = self.env.cr.dictfetchall()
        schemas = [(s['schema_name'], s['schema_name']) for s in res]
        return schemas

    def _get_table(self, schema: str, table_name: str):
        try:
            query = """SELECT table_name FROM information_schema.tables WHERE table_schema = '%s' and table_name = '%s'""" % (
                schema, table_name)
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchone()
            return res
        except Exception as e:
            return f"can not get table :{e}"

    def import_data(self):
        try:
            if not self.verify:
                raise UserError("file not verified")
            total_rows = self.odoo_import_database()
            log_create = {
                "status": const.successful_status,
                "message": const.successful_status,
                "type": const.import_type,
                "data_migration_id": self.id,
                "total_records": int(total_rows)
            }
            self.env["import.log"].create(log_create)
            if not self.verify:
                self.write({"verify": True})
            return
        except Exception as e:
            log_create = {
                "status": const.failed_status,
                "message": str(e),
                "type": const.import_type,
                "data_migration_id": self.id
            }
            self.env["import.log"].create(log_create)
            raise UserError(e)

    def scan_file(self):
        try:
            if not self.file_import and not self.url_import:
                raise UserError("file or url does not exist")
            message = const.successful_status
            status = const.successful_status
            for rec in self:
                column_file_names = []
                column_db_names = rec.get_column_db_names()
                if rec.type == const.file_import_type:
                    column_file_names = rec.read_column_from_file()
                else:
                    column_file_names =  rec.read_column_from_url()
                verify = True
                if rec.categories == const.insert_type:
                    column_db_names.remove("id")
                    if "id" in column_file_names:
                        verify = False
                        message = "id cannot exist while in creation state"
                        status = const.failed_status
                elif rec.categories == const.update_type:
                    if not self.check_id_is_exist():
                        verify = False
                        message = "id does not exist in the database"
                        status = const.failed_status
                elif not array_strings_are_equal(column_db_names, column_file_names):
                    verify = False
                    message = "column is not in the database"
                    status = const.failed_status
                rec.update_data(verify)
                log_create = {
                    "status": status,
                    "message": message,
                    "type": const.scan_type,
                    "data_migration_id": self.id
                }
                self.env["import.log"].create(log_create)
            return True
        except Exception as e:
            raise UserError(e)

    def update_data(self, verify: bool):
        try:
            data = self.env[self._name].browse(self.id)
            if data:
                data.write({"verify": verify})
        except Exception as e:
            return e

    def read_data_from_file(self):
        file_data = io.BytesIO(base64.b64decode(self.file_import))
        df = pd.read_csv(file_data,  error_bad_lines=False)
        return df

    def read_column_from_file(self) -> list:
        try:
            df = self.read_data_from_file()
            column_names = list(df.columns.values)
            return column_names
        except Exception as e:
            raise Exception(f"cannot read column: {e}")

    def read_data_from_url(self):
        response = requests.get(self.url_import)
        csv_data = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        return csv_data
        
    def read_column_from_url(self):
        df = self.read_data_from_url()
        return df.columns.tolist()

    def get_column_db_names(self) -> list:
        query = """SELECT column_name FROM information_schema.columns WHERE table_schema = '%s' AND table_name = '%s'""" % (
            self.schemas, self.tables)
        self.env.cr.execute(query)
        res = self.env.cr.dictfetchall()
        column = [r['column_name'] for r in res]
        return column

    def odoo_import_database(self):
        try:
           
            if self.type == const.url_import_type:
                df = self.read_data_from_url()
            else:
                file_data = io.BytesIO(base64.b64decode(self.file_import))
                df = pd.read_csv(file_data, error_bad_lines=False)
            columns = df.columns.tolist()
            total_rows = df.shape[0]
            if self.categories == const.insert_type:
                raw_query = """INSERT INTO {}.{} ({}) VALUES ({})""".format(self.schemas, self.tables,
                                                                            ', '.join(columns),
                                                                            ', '.join(['%s'] * len(columns)))
                for _, row in df.iterrows():
                    values = tuple([None if pd.isnull(val) else val for val in row])
                    self.env.cr.execute(raw_query, values)
            elif self.categories == const.update_type:
                update_query = """ UPDATE "{}"."{}" SET """.format(self.schemas, self.tables)
                update_columns = ', '.join(
                    '{} = %s'.format(col) for col in columns if col != 'id')  # Exclude 'id' column
                update_query += update_columns + " WHERE id = %s"
                for _, row in df.iterrows():
                    values = tuple([None if pd.isnull(val) else val for col, val in row.items() if col != 'id'])
                    values += (row['id'],)
                    self.env.cr.execute(update_query, values)

            # values = []
            # for val in row:
            #     if pd.isnull(val):
            #         values.append(None)
            #     else:
            #         values.append(val)
            #
            # values = tuple(values)

            return total_rows
        except Exception as e:
            raise Exception(f"cannot import into database: {e}")

    def check_file_type(self):
        try:
            if self.file_name.endswith(const.csv_file_type):
                return True
            return False
        except Exception as e:
            raise Exception(f"invalid file type: {e}")

    def export_column(self):
        try:
            query = """select COLUMN_NAME from INFORMATION_SCHEMA.COLUMNS where table_schema = '%s' and table_name = '%s' """ % (
                self.schemas, self.tables)
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()
            if len(res) > 0:
                column_names = [r["column_name"] for r in res]
                # Create CSV content
                output = io.StringIO()
                csv_writer = csv.writer(output)
                csv_writer.writerow(column_names)
                output.seek(0)
                csv_content = output.getvalue().encode('utf-8')
                output.close()
                file_name_download = f"{self.name}.csv"
                # Create attachment
                attachment_id = self.env['ir.attachment'].sudo().create({
                    'name': file_name_download,
                    'res_model': self._name,
                    'res_id': self.id,
                    'type': "binary",
                    'store_fname': file_name_download,
                    'datas': base64.b64encode(csv_content)  # import base64
                })

                # Construct download URL
                base_url = self.env['ir.config_parameter'].get_param('web.base.url')
                download_url = '/web/content/' + str(attachment_id.id) + '?download=true'

                # Return URL for download
                return {
                    "type": "ir.actions.act_url",
                    "url": str(base_url) + str(download_url),
                    "target": "new"
                }

        except Exception as e:
            raise UserError(e)

    def check_id_is_exist(self) -> bool:
        try:
            df = self.read_data_from_file()
            if "id" in df.columns:
                id_values = df["id"].astype(str).tolist()
                placeholders = ', '.join(['%s'] * len(id_values))
                query = """SELECT id FROM %s.%s where id in (%s)""" % (self.schemas, self.tables, placeholders)
                self.env.cr.execute(query, tuple(id_values))
                res = self.env.cr.dictfetchall()
                if len(res) == len(id_values):
                    return True
                return False
            else:
                raise UserError("No 'id' column found in CSV data")
        except Exception as e:
            raise UserError(e)

    # def _action_notification(self, title: str, message: str, type: str):
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'di@splay_notification',
    #         'params': {
    #             'title': title,
    #             'type': type,
    #             'message': message,
    #             'sticky': True,
    #         }
    #     }
    # def read_file_from_url(self):
    #     get_content = requests.get(self.url_import).content
    #     pass

    # def open_tables_wizard(self):
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'view_mode': 'form',
    #         'res_model': 'table.wizard',
    #         'view_id': self.env.ref('real_estate_ads.table_wizard_form').id,
    #         'target': 'new',
    #         'context': {
    #             'default_schema': self.schemas,
    #         },
    #     }


def array_strings_are_equal(self, data1: list, data2: list) -> Union[bool, str]:
    try:
        joined_word1 = "".join(data1)
        joined_word2 = "".join(data2)

        if joined_word1 == joined_word2:
            return True
        return False
    except Exception as e:
        raise Exception(f"can not compare data: {e}")



