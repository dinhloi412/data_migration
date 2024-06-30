import base64
import io
from typing import Union

import requests
import csv
import pandas as pd
from odoo import models, fields, api
from odoo.exceptions import UserError

from .const import successful_status, failed_status, import_type, scan_type, csv_file_type, insert_type, update_type


class DataMigration(models.Model):
    _name = 'data.migration'
    _description = 'Data Migration'

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
            if vals["type"] == "url_import":
                atts_data = requests.get(vals["url_import"])
                print(atts_data.content, "content")
                vals["file_import"] = atts_data.content
                print(atts_data.status_code, "status code")
                print(atts_data, "atts_data")
            return super(DataMigration, self).create(vals)
        except Exception as e:
            raise UserError(e)

    def write(self, vals):
        try:
            # print(vals, "vals")
            # print(vals.get("schemas"), "aaa")
            if vals.get("schemas") and vals.get("tables"):
                table = self._get_table(vals["schemas"], vals["tables"])
                if not table:
                    raise UserError("can not get table")
            if vals.get("type") and vals.get("type") == "url_import":
                atts_data = requests.get(vals["url_import"])
                vals["file_import"] = atts_data.content
            if vals.get("file_import"):
                print("check file import")
                vals["verify"] = False
            print(vals["verify"], "thisssssssssss")
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
            print(query, "query")
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchone()
            return res
        except Exception as e:
            return f"can not get table :{e}"

    def import_data(self):
        try:
            self.odoo_import_database()
            print("here")
            log_create = {
                "status": successful_status,
                "message": successful_status,
                "type": import_type,
                "data_migration_id": self.id
            }
            self.env["import.log"].create(log_create)
            print("success")
            if not self.verify:
                print("dddddddddd")
                self.sudo().env["data.migration"].write({"verify": True})
            return
        except Exception as e:
            log_create = {
                "status": failed_status,
                "message": str(e),
                "type": import_type,
                "data_migration_id": self.id
            }
            self.env["import.log"].create(log_create)
            raise UserError(e)

    def scan_file(self):
        try:
            if not self.file_import:
                raise UserError("file does not exist")
            message = failed_status
            status = failed_status
            for rec in self:
                column_db_names = rec.get_column_db_names()
                column_file_names = rec.read_column_from_file()
                verify = False
                if rec.categories == insert_type and "id" in column_db_names:
                    column_db_names.remove("id")
                print(column_db_names, "column_db_names")
                print(column_file_names, "column_file_names")
                if rec.array_strings_are_equal(column_db_names, column_file_names):
                    print("test herd")
                    verify = True
                    message = successful_status
                    status = successful_status
                rec.update_data(verify)
                log_create = {
                    "status": status,
                    "message": message,
                    "type": scan_type,
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

    def array_strings_are_equal(self, data1: list, data2: list) -> Union[bool, str]:
        try:
            print(data1, data2, "array strings are")
            joined_word1 = "".join(data1)
            joined_word2 = "".join(data2)
            print(joined_word1, "joined_word1")
            print(joined_word2, "joined_word2")

            if joined_word1 == joined_word2:
                return True
            return False
        except Exception as e:
            raise Exception(f"can not compare data: {e}")

    def _action_notification(self, title: str, message: str, type: str):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'type': type,
                'message': message,
                'sticky': True,
            }
        }

    def read_column_from_file(self) -> list:
        file_data = io.BytesIO(base64.b64decode(self.file_import))
        df = pd.read_csv(file_data)
        column_names = list(df.columns.values)
        print(column_names, "")
        return column_names

    def get_column_db_names(self) -> list:
        query = """SELECT column_name FROM information_schema.columns WHERE table_schema = '%s' AND table_name = '%s'""" % (
            self.schemas, self.tables)
        print(query, "query")
        self.env.cr.execute(query)
        res = self.env.cr.dictfetchall()
        column = [r['column_name'] for r in res]
        print(column, "column")
        return column

    def odoo_import_database(self):
        try:
            file_data = io.BytesIO(base64.b64decode(self.file_import))
            df = pd.read_csv(file_data)
            df = df.where(pd.notnull(df), None)
            columns = df.columns.tolist()
            print(columns, "columns")
            raw_query = ""
            print(self.categories, "self.type")
            if self.categories == insert_type:
                raw_query = """INSERT INTO {}.{} ({}) VALUES ({})""".format(self.schemas, self.tables,
                                                                            ', '.join(columns),
                                                                            ', '.join(['%s'] * len(columns)))
                for _, row in df.iterrows():
                    values = tuple([None if pd.isnull(val) else val for val in row])
                    self.env.cr.execute(raw_query, values)
            elif self.categories == update_type:
                update_query = """ UPDATE "{}"."{}" SET """.format(self.schemas, self.tables)
                update_columns = ', '.join('{} = %s'.format(col) for col in columns)
                update_query += update_columns + " WHERE id = %s"
                raw_query = update_query
                for _, row in df.iterrows():
                    values = tuple([None if pd.isnull(val) else val for val in row])
                    values += (row['id'],)

                    self.env.cr.execute(update_query, values)

            print(raw_query, "raw_query")

            # values = []
            # for val in row:
            #     if pd.isnull(val):
            #         values.append(None)
            #     else:
            #         values.append(val)
            #
            # values = tuple(values)

            return True
        except Exception as e:
            raise Exception(f"cannot import into database: {e}")

    def check_file_type(self):
        try:
            print(self.file_name.endswith, "self.file_name.endswith")
            if self.file_name.endswith(csv_file_type):
                return True
            return False
        except Exception as e:
            raise Exception(f"invalid file type: {e}")

    def export_column(self):
        try:
            print("export column")
            query = """select COLUMN_NAME from INFORMATION_SCHEMA.COLUMNS where table_schema = '%s' and table_name = '%s' """ % (
                self.schemas, self.tables)
            print(query, "query1")
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()
            print(res, "res")
            if len(res) > 0:
                column_names = [r["column_name"] for r in res]
                # column_names = list(res[0].values())
                print(column_names, "ccolumn_names")
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

            # print(data, "data")
        except Exception as e:
            raise UserError("failed to export column")

    def check_id_is_exist(self):
        pass
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
