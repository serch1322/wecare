# Part of Odoo. See LICENSE file for full copyright and licensing details.
from __future__ import division

import base64
from datetime import time as dt_time, timedelta
import logging
import re
import time
from io import BytesIO
from itertools import groupby
from calendar import monthrange
import requests
from pytz import timezone as pytz_timezone

from lxml import etree, objectify
from werkzeug import url_encode
from zeep import Client
from zeep.transports import Transport

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError, UserError
from odoo.tools import DEFAULT_SERVER_TIME_FORMAT
from odoo.tools.xml_utils import _check_with_xsd

_logger = logging.getLogger(__name__)


PAYSLIP_TEMPLATE = 'l10n_mx_edi_payslip.payroll12'
CFDI_XSLT_CADENA = 'l10n_mx_edi/data/3.3/cadenaoriginal.xslt'


def create_list_html(array):
    """Convert an array of string to a html list.
    :param list array: A list of strings
    :return: empty string if not array, an html list otherwise.
    :rtype: str"""
    if not array:  # pragma: no cover
        return ''  # pragma: no cover
    msg = ''
    for item in array:
        msg += '<li>' + item + '</li>'
    return '<ul>' + msg + '</ul>'


class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _inherit = ['hr.payslip', 'mail.thread', 'l10n_mx_edi.pac.sw.mixin']

    l10n_mx_edi_payment_date = fields.Date(
        'Payment Date', required=True, readonly=True,
        states={'draft': [('readonly', False)]},
        default=time.strftime('%Y-%m-01'), help='Save the payment date that '
        'will be added on CFDI.')
    l10n_mx_edi_cfdi_name = fields.Char(
        string='CFDI name', copy=False, readonly=True,
        help='The attachment name of the CFDI.')
    l10n_mx_edi_cfdi = fields.Binary(
        'CFDI content', copy=False, readonly=True,
        help='The cfdi xml content encoded in base64.',
        compute='_compute_cfdi_values')
    l10n_mx_edi_overtime_line_ids = fields.One2many(
        'hr.payslip.overtime', 'payslip_id', 'Extra hours',
        readonly=True, states={'draft': [('readonly', False)], 'verify': [('readonly', False)]},
        help='Used in XML like optional node to express the extra hours '
        'applicable by employee.', copy=True)
    l10n_mx_edi_pac_status = fields.Selection(
        [('retry', 'Retry'),
         ('to_sign', 'To sign'),
         ('signed', 'Signed'),
         ('to_cancel', 'To cancel'),
         ('cancelled', 'Cancelled')], 'PAC status',
        help='Refers to the status of the payslip inside the PAC.',
        readonly=True, copy=False)
    l10n_mx_edi_sat_status = fields.Selection(
        [('none', 'State not defined'),
         ('undefined', 'Not Synced Yet'),
         ('not_found', 'Not Found'),
         ('cancelled', 'Cancelled'),
         ('valid', 'Valid')], 'SAT status',
        help='Refers to the status of the payslip inside the SAT system.',
        readonly=True, copy=False, required=True, tracking=True,
        default='undefined')
    l10n_mx_edi_cfdi_uuid = fields.Char(
        'Fiscal Folio', copy=False, readonly=True,
        help='Folio in electronic payroll, is returned by SAT when send to '
        'stamp.', compute='_compute_cfdi_values')
    l10n_mx_edi_cfdi_supplier_rfc = fields.Char(
        'Supplier RFC', copy=False, readonly=True,
        help='The supplier tax identification number.',
        compute='_compute_cfdi_values')
    l10n_mx_edi_cfdi_customer_rfc = fields.Char(
        'Customer RFC', copy=False, readonly=True,
        help='The customer tax identification number.',
        compute='_compute_cfdi_values')
    l10n_mx_edi_cfdi_amount = fields.Float(
        'Total Amount', copy=False, readonly=True,
        help='The total amount reported on the cfdi.',
        compute='_compute_cfdi_values')
    l10n_mx_edi_action_title_ids = fields.One2many(
        'hr.payslip.action.titles', 'payslip_id', string='Action or Titles',
        help='If the payslip have perceptions with code 045, assign here the '
        'values to the attribute in XML, use the perception type to indicate '
        'if apply to exempt or taxed.')
    l10n_mx_edi_extra_node_ids = fields.One2many(
        'hr.payslip.extra.perception', 'payslip_id',
        string='Extra data to perceptions',
        help='If the payslip have perceptions with code in 022, 023 or 025,'
        'must be created a record with data that will be assigned in the '
        'node "SeparacionIndemnizacion", or if the payslip have perceptions '
        'with code in 039 or 044 must be created a record with data that will '
        'be assigned in the node "JubilacionPensionRetiro". Only must be '
        'created a record by node.')
    l10n_mx_edi_balance_favor = fields.Float(
        'Balance in Favor', help='If the payslip include other payments, and '
        'one of this records have the code 004 is need add the balance in '
        'favor to assign in node "CompensacionSaldosAFavor".')
    l10n_mx_edi_comp_year = fields.Integer(
        'Year', help='If the payslip include other payments, and '
        'one of this records have the code 004 is need add the year to assign '
        'in node "CompensacionSaldosAFavor".')
    l10n_mx_edi_remaining = fields.Float(
        'Remaining', help='If the payslip include other payments, and '
        'one of this records have the code 004 is need add the remaining to '
        'assign in node "CompensacionSaldosAFavor".')
    l10n_mx_edi_source_resource = fields.Selection([
        ('IP', 'Own income'),
        ('IF', 'Federal income'),
        ('IM', 'Mixed income')], 'Source Resource',
        help='Used in XML to identify the source of the resource used '
        'for the payment of payroll of the personnel that provides or '
        'performs a subordinate or assimilated personal service to salaries '
        'in the dependencies. This value will be set in the XML attribute '
        '"OrigenRecurso" to node "EntidadSNCF".')
    l10n_mx_edi_amount_sncf = fields.Float(
        'Own resource', help='When the attribute in "Source Resource" is "IM" '
        'this attribute must be added to set in the XML attribute '
        '"MontoRecursoPropio" in node "EntidadSNCF", and must be less that '
        '"TotalPercepciones" + "TotalOtrosPagos"')
    l10n_mx_edi_cfdi_string = fields.Char(
        'CFDI Original String', help='Attribute "cfdi_cadena_original" '
        'returned by PAC request when is stamped the CFDI, this attribute is '
        'used on report.')
    l10n_mx_edi_cfdi_certificate_id = fields.Many2one(
        'l10n_mx_edi.certificate', string='Certificate', copy=False,
        readonly=True, help='The certificate used during the generation of '
        'the cfdi.', compute='_compute_cfdi_values')
    l10n_mx_edi_origin = fields.Char(
        string='CFDI Origin', copy=False,
        help='In some cases the payroll must be regenerated to fix data in it.'
        ' In that cases is necessary this field filled, the format is: '
        '\n04|UUID1, UUID2, ...., UUIDn.\n'
        'Example:\n"04|89966ACC-0F5C-447D-AEF3-3EED22E711EE,'
        '89966ACC-0F5C-447D-AEF3-3EED22E711EE"')
    l10n_mx_edi_expedition_date = fields.Date(
        string='Payslip date', readonly=True, copy=False, index=True,
        states={'draft': [('readonly', False)]},
        help="Keep empty to use the current date")
    l10n_mx_edi_time_payslip = fields.Char(
        string='Time payslip', readonly=True, copy=False,
        states={'draft': [('readonly', False)]},
        help="Keep empty to use the current México central time")
    sent = fields.Boolean(readonly=True, default=False, copy=False,
                          help="It indicates that the payslip has been sent.")
    # Add parameter copy=True
    input_line_ids = fields.One2many(copy=True)

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    @api.model
    def l10n_mx_edi_get_tfd_etree(self, cfdi):
        """Get the TimbreFiscalDigital node from the cfdi.

        :param cfdi: The cfdi as etree
        :type cfdi: etree
        :return: the TimbreFiscalDigital node
        :rtype: etree
        """
        # TODO - This method is the same that invoice.
        if not hasattr(cfdi, 'Complemento'):
            return None
        attribute = 'tfd:TimbreFiscalDigital[1]'
        namespace = {'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'}
        node = cfdi.Complemento.xpath(attribute, namespaces=namespace)
        return node[0] if node else None

    @api.model
    def l10n_mx_edi_get_payroll_etree(self, cfdi):
        """Get the Complement node from the cfdi.
        :param cfdi: The cfdi as etree
        :type cfdi: etree
        :return: the Payment node
        :rtype: etree
        """
        if not hasattr(cfdi, 'Complemento'):
            return None
        attribute = '//nomina12:Nomina'
        namespace = {'nomina12': 'http://www.sat.gob.mx/nomina12'}
        node = cfdi.Complemento.xpath(attribute, namespaces=namespace)
        return node[0] if node else None

    def _get_extra_nodes(self):
        """Create the extra nodes dict(s)
        :return: a list with the extra nodes to apply
        :rtype: list
        """
        self.ensure_one()
        nodes = []
        categ_g = self.env.ref('l10n_mx_edi_payslip.hr_salary_rule_category_perception_mx_taxed').id
        categ_e = self.env.ref('l10n_mx_edi_payslip.hr_salary_rule_category_perception_mx_exempt').id
        perceptions = self.line_ids.search([
            ('id', 'in', self.line_ids.ids),
            ('category_id', 'in', [categ_g, categ_e]),
            ('total', '!=', '0'),
            ('salary_rule_id.l10n_mx_edi_code', 'in', ['022', '023', '025', '039', '044']),
        ])
        separation_line_ids = perceptions.search([
            ('id', 'in', perceptions.ids),
            ('salary_rule_id.l10n_mx_edi_code', 'in', ('022', '023', '025')),
        ])
        total = round(sum(separation_line_ids.mapped('total')), 2)
        if separation_line_ids and total:
            seniority = self.contract_id.get_seniority(date_to=self.date_to)
            years = round(seniority.get('years'), 0) if seniority.get(
                'months') > 6 or (seniority.get('months') == 6 and seniority
                                  .get('days') > 1) else seniority.get('years')
            nodes.append({
                'node': 'separation',
                'amount_total': total,
                'last_salary': self.contract_id.wage,
                'service_years': years,
                'non_accumulable_income': (total - self.contract_id.wage) if (
                    total > self.contract_id.wage) else 0,
                'accumulable_income': self.contract_id.wage if (
                    total > self.contract_id.wage) else total})
        retirement_line_ids = perceptions.filtered(
            lambda line: line.salary_rule_id.l10n_mx_edi_code == '039')
        retirement_partial_ids = perceptions.filtered(
            lambda line: line.salary_rule_id.l10n_mx_edi_code == '044')
        if retirement_line_ids and retirement_partial_ids:
            raise UserError(
                _("You have perceptions with code 039 and 044. "
                  "You can only have one of them."))
        retirement_line_ids = retirement_line_ids or retirement_partial_ids
        total = round(sum(retirement_line_ids.mapped('total')), 2)
        if retirement_line_ids and total:
            nodes.append({
                'node': 'retirement',
                'amount_total': total,
                'amount_daily': self.contract_id.wage/30 if (
                    retirement_line_ids[0].salary_rule_id.l10n_mx_edi_code == '044') else 0,
                'non_accumulable_income': (total - self.contract_id.wage) if (
                    total > self.contract_id.wage) else 0,
                'accumulable_income': self.contract_id.wage if (
                    total > self.contract_id.wage) else total
            })
        self.l10n_mx_edi_extra_node_ids.unlink()
        return nodes

    @api.model
    def l10n_mx_edi_generate_cadena(self, xslt_path, cfdi_as_tree):
        """Generate the cadena of the cfdi based on an xslt file.
        The cadena is the sequence of data formed with the information
        contained within the cfdi. This can be encoded with the certificate
        to create the digital seal. Since the cadena is generated with the
        payslip data, any change in it will be noticed resulting in a different
        cadena and so, ensure the payslip has not been modified.
        :param xslt_path: The path to the xslt file.
        :type xslt_path: str
        :param cfdi_as_tree: The cfdi converted as a tree
        :type cfdi_as_tree: etree
        :return: A string computed with the payslip data called the cadena
        :rtype: str
        """
        # TODO - Same method that on invoice
        self.ensure_one()
        xslt_root = etree.parse(tools.file_open(xslt_path))
        return str(etree.XSLT(xslt_root)(cfdi_as_tree))

    def get_cfdi_related(self):
        """To node CfdiRelacionados get documents related with each payslip
        from l10n_mx_edi_origin, hope the next structure:
            relation type|UUIDs separated by ,"""
        # TODO - Same method that on invoice
        self.ensure_one()
        if not self.l10n_mx_edi_origin:
            return {}
        origin = self.l10n_mx_edi_origin.split('|')
        uuids = origin[1].split(',') if len(origin) > 1 else []
        return {
            'type': origin[0],
            'related': [u.strip() for u in uuids],
        }

    def l10n_mx_edi_is_required(self):
        self.ensure_one()
        company = self.company_id or self.contract_id.company_id
        return company.country_id == self.env.ref('base.mx')

    def l10n_mx_edi_log_error(self, message):
        # TODO - Same method that on invoice
        self.ensure_one()
        self.message_post(
            body=_('Error during the process: %s') % message,
            subtype='account.mt_invoice_validated')

    @api.model
    def _get_l10n_mx_edi_cadena(self):
        self.ensure_one()
        # get the xslt path
        xslt_path = CFDI_XSLT_CADENA
        # get the cfdi as eTree
        cfdi = self.l10n_mx_edi_get_xml_etree()
        # return the cadena
        return self.env['account.move'].l10n_mx_edi_generate_cadena(
            xslt_path, cfdi)

    # -------------------------------------------------------------------------
    # SAT/PAC service methods
    # -------------------------------------------------------------------------

    @api.model
    def _l10n_mx_edi_solfact_info(self, company_id, service_type):
        test = company_id.l10n_mx_edi_pac_test_env
        username = company_id.l10n_mx_edi_pac_username
        password = company_id.l10n_mx_edi_pac_password
        url = ('https://testing.solucionfactible.com/ws/services/Timbrado?wsdl'
               if test else
               'https://solucionfactible.com/ws/services/Timbrado?wsdl')
        return {
            'url': url,
            'multi': False,  # TODO: implement multi
            'username': 'testing@solucionfactible.com' if test else username,
            'password': 'timbrado.SF.16672' if test else password,
        }

    def _l10n_mx_edi_solfact_sign(self, pac_info):
        """SIGN for Solucion Factible.
        """
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        for record in self:
            cfdi = record.l10n_mx_edi_cfdi
            try:
                transport = Transport(timeout=20)
                client = Client(url, transport=transport)
                response = client.service.timbrar(
                    username, password, cfdi, False)
            except BaseException as e:
                record.l10n_mx_edi_log_error(str(e))
                continue
            msg = getattr(response.resultados[0], 'mensaje', None)
            code = getattr(response.resultados[0], 'status', None)
            xml_signed = getattr(response.resultados[0], 'cfdiTimbrado', None)
            record._l10n_mx_edi_post_sign_process(xml_signed, code, msg)

    def _l10n_mx_edi_solfact_cancel(self, pac_info):
        """CANCEL for Solucion Factible.
        """
        # TODO - Same method that on invoice
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        for record in self:
            uuids = [record.l10n_mx_edi_cfdi_uuid]
            certificate_id = record.sudo().l10n_mx_edi_cfdi_certificate_id
            cer_pem = base64.encodebytes(certificate_id.get_pem_cer(
                certificate_id.content))
            key_pem = base64.encodebytes(certificate_id.get_pem_key(
                certificate_id.key, certificate_id.password))
            key_password = certificate_id.password
            try:
                transport = Transport(timeout=20)
                client = Client(url, transport=transport)
                response = client.service.cancelar(
                    username, password, uuids, cer_pem, key_pem, key_password)
            except BaseException as e:
                record.l10n_mx_edi_log_error(str(e))
                continue
            msg = getattr(response.resultados[0], 'mensaje', None)
            code = getattr(response.resultados[0], 'statusUUID', None)
            cancelled = code in ('201', '202')
            record._l10n_mx_edi_post_cancel_process(cancelled, code, msg)

    def _l10n_mx_edi_finkok_info(self, company_id, service_type):
        test = company_id.l10n_mx_edi_pac_test_env
        username = company_id.l10n_mx_edi_pac_username
        password = company_id.l10n_mx_edi_pac_password
        if service_type == 'sign':
            url = (
                'http://demo-facturacion.finkok.com/servicios/soap/stamp.wsdl'
                if test else
                'http://facturacion.finkok.com/servicios/soap/stamp.wsdl')
        else:
            url = (
                'http://demo-facturacion.finkok.com/servicios/soap/cancel.wsdl'
                if test else
                'http://facturacion.finkok.com/servicios/soap/cancel.wsdl')
        return {
            'url': url,
            'multi': False,  # TODO: implement multi
            'username': 'cfdi@vauxoo.com' if test else username,
            'password': 'vAux00__' if test else password,
        }

    def _l10n_mx_edi_finkok_sign(self, pac_info):
        """SIGN for Finkok.
        """
        # TODO - Same method that on invoice
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        for record in self:
            cfdi = base64.decodestring(record.l10n_mx_edi_cfdi)
            try:
                transport = Transport(timeout=20)
                client = Client(url, transport=transport)
                response = client.service.stamp(cfdi, username, password)
            except BaseException as e:
                record.l10n_mx_edi_log_error(str(e))
                continue
            code = 0
            msg = None
            if response.Incidencias:
                code = getattr(
                    response.Incidencias.Incidencia[0], 'CodigoError', None)
                msg = getattr(
                    response.Incidencias.Incidencia[0],
                    'MensajeIncidencia', None)
            xml_signed = getattr(response, 'xml', None)
            if xml_signed:
                xml_signed = base64.b64encode(xml_signed.encode('utf-8'))
            record._l10n_mx_edi_post_sign_process(xml_signed, code, msg)

    def _l10n_mx_edi_finkok_cancel(self, pac_info):
        """CANCEL for Finkok.
        """
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        for record in self:
            uuid = record.l10n_mx_edi_cfdi_uuid
            certificate_id = record.sudo().l10n_mx_edi_cfdi_certificate_id
            company_id = self.company_id or self.contract_id.company_id
            cer_pem = certificate_id.get_pem_cer(certificate_id.content)
            key_pem = certificate_id.get_pem_key(certificate_id.key, certificate_id.password)
            cancelled = False
            code = False
            try:
                transport = Transport(timeout=20)
                client = Client(url, transport=transport)
                uuid_type = client.get_type("ns0:stringArray")()
                uuid_type.string = [uuid]
                payslips_list = client.get_type('ns1:UUIDS')(uuid_type)
                response = client.service.cancel(
                    payslips_list, username, password,
                    company_id.vat, cer_pem, key_pem)
            except BaseException as e:
                record.l10n_mx_edi_log_error(str(e))
                continue
            if not getattr(response, 'Folios', None):
                code = getattr(response, 'CodEstatus', None)
                msg = _("Cancelling got an error") if code else _(
                    'A delay of 2 hours has to be respected before to cancel')
            else:
                code = getattr(response.Folios.Folio[0], 'EstatusUUID', None)
                cancelled = code in ('201', '202')  # cancelled or previously cancelled  # noqa
                # no show code and response message if cancel was success
                code = '' if cancelled else code
                msg = '' if cancelled else _("Cancelling got an error")
            record._l10n_mx_edi_post_cancel_process(cancelled, code, msg)

    def _l10n_mx_edi_call_service(self, service_type):
        """Call the right method according to the pac_name,
        it's info returned by the '_l10n_mx_edi_%s_info' % pac_name'
        method and the service_type passed as parameter.
        :param service_type: sign or cancel
        :type service_type: string
        """
        # Regroup the payslip by company (= by pac)
        comp_x_records = groupby(
            self, lambda r: r.company_id or r.contract_id.company_id)
        for company_id, records in comp_x_records:
            pac_name = company_id.l10n_mx_edi_pac
            if not pac_name:
                continue
            # Get the informations about the pac
            pac_info_func = '_l10n_mx_edi_%s_info' % pac_name
            service_func = '_l10n_mx_edi_%s_%s' % (pac_name, service_type)
            pac_info = getattr(self, pac_info_func)(company_id, service_type)
            # Call the service with payslips one by one or all together according to the 'multi' value.  # noqa
            multi = pac_info.pop('multi', False)
            if multi:
                # rebuild the recordset
                contract_ids = self.search(
                    [('company_id', '=', company_id.id)])
                records = self.search(
                    [('id', 'in', self.ids),
                     '|', ('company_id', '=', company_id.id),
                     ('contract_id', 'in', contract_ids.ids)])
                getattr(records, service_func)(pac_info)
            else:
                for record in records:
                    getattr(record, service_func)(pac_info)

    def _l10n_mx_edi_post_sign_process(self, xml_signed, code=None, msg=None):
        """Post process the results of the sign service.

        :param xml_signed: the xml signed datas codified in base64
        :type xml_signed: base64
        :param code: an eventual error code
        :type code: string
        :param msg: an eventual error msg
        :type msg: string
        """
        self.ensure_one()
        if xml_signed:
            body_msg = _('The sign service has been called with success')
            # Update the pac status
            self.l10n_mx_edi_pac_status = 'signed'
            self.l10n_mx_edi_cfdi = xml_signed
            # Update the content of the attachment
            attachment_id = self.l10n_mx_edi_retrieve_last_attachment()
            attachment_id.write({
                'datas': xml_signed,
                'mimetype': 'application/xml'
            })
            post_msg = [_('The content of the attachment has been updated')]
        else:
            body_msg = _('The sign service requested failed')
            post_msg = []
        if code:
            post_msg.extend([_('Code: ') + str(code)])
        if msg:
            post_msg.extend([_('Message: ') + msg])
        self.message_post(
            body=body_msg + create_list_html(post_msg),
            subtype='account.mt_invoice_validated')

    def _l10n_mx_edi_sign(self):
        """Call the sign service with records that can be signed.
        """
        records = self.search([
            ('l10n_mx_edi_pac_status', 'not in',
             ['signed', 'to_cancel', 'cancelled', 'retry']),
            ('id', 'in', self.ids)])
        records._l10n_mx_edi_call_service('sign')

    def _l10n_mx_edi_post_cancel_process(self, cancelled, code=None, msg=None):
        """Post process the results of the cancel service.

        :param cancelled: is the cancel has been done with success
        :type cancelled: bool
        :param code: an eventual error code
        :type code: string
        :param msg: an eventual error msg
        :type msg: string
        """

        self.ensure_one()
        if cancelled:
            body_msg = _('The cancel service has been called with success')
            self.l10n_mx_edi_pac_status = 'cancelled'
        else:
            body_msg = _('The cancel service requested failed')
        post_msg = []
        if code:
            post_msg.extend([_('Code: ') + str(code)])
        if msg:
            post_msg.extend([_('Message: ') + msg])
        self.message_post(
            body=body_msg + create_list_html(post_msg),
            subtype='account.mt_invoice_validated')

    def _l10n_mx_edi_cancel(self):
        """Call the cancel service with records that can be signed.
        """
        records = self.search([
            ('l10n_mx_edi_pac_status', 'in',
             ['to_sign', 'signed', 'to_cancel', 'retry']),
            ('id', 'in', self.ids)])
        for record in records:
            if record.l10n_mx_edi_pac_status in ['to_sign', 'retry']:
                record.l10n_mx_edi_pac_status = 'cancelled'
                record.message_post(body=_(
                    'The cancel service has been called with success'),
                    subtype='account.mt_invoice_validated')
            else:
                record.l10n_mx_edi_pac_status = 'to_cancel'
        records = self.search([
            ('l10n_mx_edi_pac_status', '=', 'to_cancel'),
            ('id', 'in', self.ids)])
        records._l10n_mx_edi_call_service('cancel')

    # -------------------------------------------------------------------------
    # Payslip methods
    # -------------------------------------------------------------------------

    @api.onchange('employee_id', 'struct_id', 'contract_id', 'date_from', 'date_to')  # noqa
    def _onchange_employee(self):
        res = super(HrPayslip, self)._onchange_employee()
        self.company_id = (self.employee_id.company_id or
                           self.contract_id.company_id or
                           self.env.user.company_id)
        return res

    def action_payslip_cancel(self):
        """Overwrite method when state is done, to allow cancel payslip in done
        """
        to_cancel = self.filtered(lambda r: r.state == 'done')
        to_cancel.write({'state': 'cancel'})
        self.refresh()
        res = super(HrPayslip, self).action_payslip_cancel()
        mx_payslip = self.filtered(lambda r: r.l10n_mx_edi_is_required())
        mx_payslip._l10n_mx_edi_cancel()
        return res

    def action_payroll_sent(self):
        """Open a window to compose an email, with the edi payslip template
        message loaded by default"""
        self.ensure_one()
        template = self.env.ref(
            'l10n_mx_edi_payslip.email_template_edi_payroll', False)
        compose_form = self.env.ref(
            'mail.email_compose_message_wizard_form', False)
        ctx = self._context.copy()
        ctx['default_model'] = 'hr.payslip'
        ctx['default_model'] = 'hr.payslip'
        ctx['default_res_id'] = self.id
        ctx['default_use_template'] = bool(template)
        ctx['default_template_id'] = template.id or False
        ctx['default_composition_mode'] = 'comment'
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

    @api.depends('l10n_mx_edi_cfdi_name')
    def _compute_cfdi_values(self):
        """Fill the payroll fields from the CFDI values."""
        for record in self:
            attachment_id = record.l10n_mx_edi_retrieve_last_attachment()
            record.l10n_mx_edi_cfdi_uuid = None
            if not attachment_id:
                record.l10n_mx_edi_cfdi = None
                continue
            # At this moment, the attachment contains the file size in its
            # 'datas' field because to save some memory, the attachment will
            # store its data on the physical disk.
            # To avoid this problem, we read the 'datas' directly on the disk.
            datas = attachment_id._file_read(attachment_id.store_fname)
            record.l10n_mx_edi_cfdi = datas
            tree = record.l10n_mx_edi_get_xml_etree(base64.decodebytes(datas))
            # if already signed, extract uuid
            tfd_node = record.l10n_mx_edi_get_tfd_etree(tree)
            if tfd_node is not None:
                record.l10n_mx_edi_cfdi_uuid = tfd_node.get('UUID')
            record.l10n_mx_edi_cfdi_amount = tree.get(
                'Total', tree.get('total'))
            record.l10n_mx_edi_cfdi_supplier_rfc = tree.Emisor.get(
                'Rfc', tree.Emisor.get('rfc'))
            record.l10n_mx_edi_cfdi_customer_rfc = tree.Receptor.get(
                'Rfc', tree.Receptor.get('rfc'))
            record.l10n_mx_edi_cfdi_certificate_id = self.env[
                'l10n_mx_edi.certificate'].sudo().search([
                    ('serial_number', '=', tree.get(
                        'NoCertificado', tree.get('noCertificado')))],
                    limit=1)

    def action_payslip_draft(self):
        for record in self.filtered('l10n_mx_edi_cfdi_uuid'):
            record.l10n_mx_edi_origin = '04|%s' % record.l10n_mx_edi_cfdi_uuid
        self.write({
            'l10n_mx_edi_expedition_date': False,
            'l10n_mx_edi_time_payslip': False,
        })
        return super(HrPayslip, self).action_payslip_draft()

    def action_payslip_done(self):
        """Generates the cfdi attachments for mexican companies when validated.
        """
        if not self.user_has_groups('l10n_mx_edi_payslip.allow_validate_payslip'):
            raise UserError(_(
                "Only Managers who are allow to validate payslip can perform this operation"))
        result = super(HrPayslip, self).action_payslip_done()
        for record in self.filtered(lambda r: r.l10n_mx_edi_is_required()):
            # Assign overtimes to avoid write in that records
            self.env['hr.payslip.overtime'].search([
                ('employee_id', '=', record.employee_id.id),
                ('name', '>=', record.date_from),
                ('name', '<=', record.date_to),
            ]).write({'payslip_id': record.id})
            company = record.company_id or record.contract_id.company_id
            partner = company.partner_id.commercial_partner_id
            tz = self.env['account.move']._l10n_mx_edi_get_timezone(
                partner.state_id.code)
            date_mx = fields.datetime.now(tz)
            if not record.l10n_mx_edi_expedition_date:
                record.l10n_mx_edi_expedition_date = date_mx.date()
            if not record.l10n_mx_edi_time_payslip:
                record.l10n_mx_edi_time_payslip = date_mx.strftime(
                    DEFAULT_SERVER_TIME_FORMAT)
            record.l10n_mx_edi_cfdi_name = ('%s-MX-Payroll-3-3.xml' % (
                record.number)).replace('/', '')
            record._l10n_mx_edi_retry()
            record.employee_id.loan_ids.filtered(
                lambda loan: loan.payslips_count < loan.payment_term).write({
                    'payslip_ids': [(4, record.id)],
                })
        return result

    def _prepare_line_values(self, line, account_id, date, debit, credit):
        # Adding payslip lines to account.move.line
        line_values = super(HrPayslip, self)._prepare_line_values(line, account_id, date, debit, credit)
        line_values['l10n_mx_edi_payslip_line_ids'] = [(6, 0, [line.id])]
        return line_values

    def _get_existing_lines(self, line_ids, line, account_id, debit, credit):
        if line.slip_id.company_id.l10n_mx_edi_not_global_entry or not line.salary_rule_id.l10n_mx_group_entry:
            return False
        existing_lines = super(HrPayslip, self)._get_existing_lines(line_ids, line, account_id, debit, credit)
        if existing_lines:
            existing_lines['l10n_mx_edi_payslip_line_ids'][0][2].append(line.id)
        return existing_lines

    def compute_sheet(self):
        if (self.filtered(lambda r: r.l10n_mx_edi_is_required()) and
                not self.env.user.company_id.l10n_mx_edi_minimum_wage):
            raise ValidationError(_(
                'Please, you set the minimum wage in Mexico to that you '
                'can calculate the payroll'))
        res = super(HrPayslip, self).compute_sheet()
        for payslip in self.filtered(lambda slip: slip.state in ['draft', 'verify']):
            payslip.write({
                'l10n_mx_edi_extra_node_ids': [
                    (0, 0, node) for node in payslip._get_extra_nodes()]})
            payslip.line_ids.filtered(lambda l: l.amount == 0 and l.category_id.code != 'NETSA').unlink()
        return res

    def action_refresh_from_work_entries(self):
        # Refresh the whole payslip in case the HR has modified some work entries
        # after the payslip generation
        self.ensure_one()
        self._onchange_employee()
        self.compute_sheet()

    def _l10n_mx_edi_retry(self):
        """Try to generate the cfdi attachment and then, sign it."""
        for record in self:
            cfdi_values = record._l10n_mx_edi_create_cfdi()
            error = cfdi_values.pop('error', None)
            cfdi = cfdi_values.pop('cfdi', None)
            if error:
                # cfdi failed to be generated
                record.l10n_mx_edi_pac_status = 'retry'
                record.message_post(body=error)
                continue
            # cfdi has been successfully generated
            record.l10n_mx_edi_pac_status = 'to_sign'

            ctx = self.env.context.copy()
            ctx.pop('default_type', False)

            attach_id = self.env['ir.attachment'].with_context(ctx).create({
                'name': record.l10n_mx_edi_cfdi_name,
                'res_id': record.id,
                'res_model': record._name,
                'datas': base64.encodebytes(cfdi),
                'description': 'Mexican payroll',
            })
            record.message_post(
                body=_('CFDI document generated (may be not signed)'),
                attachment_ids=[attach_id.id])
            record._l10n_mx_edi_sign()

    @api.model
    def l10n_mx_edi_retrieve_attachments(self):
        """Retrieve all the CFDI attachments generated for this payroll.
        Returns:
            recordset: An ir.attachment recordset"""
        self.ensure_one()
        if not self.l10n_mx_edi_cfdi_name:
            return []
        domain = [
            ('res_id', '=', self.id),
            ('res_model', '=', self._name),
            ('name', '=', self.l10n_mx_edi_cfdi_name)]
        return self.env['ir.attachment'].search(domain)

    @api.model
    def l10n_mx_edi_retrieve_last_attachment(self):
        attachment_ids = self.l10n_mx_edi_retrieve_attachments()
        return attachment_ids[0] if attachment_ids else None

    @api.model
    def l10n_mx_edi_get_xml_etree(self, cfdi=None):
        """Get an objectified tree representing the cfdi.
        If the cfdi is not specified, retrieve it from the attachment.
        :param str cfdi: The cfdi as string
        :type: str
        :return: An objectified tree
        :rtype: objectified"""
        # TODO helper which is not of too much help and should be removed
        self.ensure_one()
        if cfdi is None:
            cfdi = base64.decodebytes(self.l10n_mx_edi_cfdi)
        return objectify.fromstring(cfdi)

    @staticmethod
    def _l10n_mx_get_serie_and_folio(number):
        # TODO - Same method on invoice
        values = {'serie': None, 'folio': None}
        number_matchs = list(re.finditer(r'\d+', number or ''))
        if number_matchs:
            last_number_match = number_matchs[-1]
            values['serie'] = number[:last_number_match.start()] or None
            values['folio'] = last_number_match.group().lstrip('0') or None
        return values

    @staticmethod
    def _get_string_cfdi(text, size=100):
        """Replace from text received the characters that are not found in the
        regex. This regex is taken from SAT documentation
        https://goo.gl/C9sKH6
        text: Text to remove extra characters
        size: Cut the string in size len
        Ex. 'Product ABC (small size)' - 'Product ABC small size'"""
        if not text:
            return None
        text = text.replace('|', ' ')
        return text.strip()[:size]

    def _l10n_mx_edi_create_cfdi_values(self):
        """Create the values to fill the CFDI template."""
        self.ensure_one()
        payroll = self._l10n_mx_edi_create_payslip_values()
        if payroll.get('error', False):
            return payroll
        subtotal = payroll['total_other'] + payroll['total_perceptions']
        deduction = payroll['total_deductions']
        company = self.company_id or self.contract_id.company_id
        values = {
            'record': self,
            'supplier': company.partner_id.commercial_partner_id,
            'customer': self.employee_id.address_home_id.commercial_partner_id,
            'amount_untaxed': '%.2f' % abs(subtotal or 0.0),
            'amount_discount': '%.2f' % abs(deduction or 0.0),
            'taxes': {},
            'outsourcing': [],  # TODO - How set the outsourcing?
        }

        values.update(self._l10n_mx_get_serie_and_folio(self.number))

        values.update(payroll)
        return values

    def _l10n_mx_edi_create_payslip_values(self):
        self.ensure_one()
        employee = self.employee_id
        if not self.contract_id:
            return {'error': _('Employee has not a contract and is required')}
        seniority = self.contract_id.get_seniority(
            date_to=self.date_to)['days'] / 7
        payroll = {
            'record': self,
            'company': self.company_id or self.contract_id.company_id,
            'employee': self.employee_id,
            'payslip_type': self.struct_id.type_id.l10n_mx_edi_type or 'O',
            'number_of_days': int(sum(self.worked_days_line_ids.mapped(
                'number_of_days'))),
            'date_start': self.contract_id.date_start,
            'seniority_emp': 'P%sW' % int(seniority),
        }
        payroll.update(employee.get_cfdi_employee_data(self.contract_id))
        payroll.update(self.get_cfdi_perceptions_data())
        payroll.update(self.get_cfdi_deductions_data())
        payroll.update(self.get_cfdi_other_payments_data())
        payroll['inability_data'] = lambda i, p: p._get_inability_data(i)
        return payroll

    def get_cfdi_perceptions_data(self):
        categ_g = self.env.ref(
            'l10n_mx_edi_payslip.hr_salary_rule_category_perception_mx_taxed')
        categ_e = self.env.ref(
            'l10n_mx_edi_payslip.hr_salary_rule_category_perception_mx_exempt')
        perceptions = self.line_ids.filtered(
            lambda r: r.category_id in [categ_g, categ_e] and r.total)
        total_taxed = round(sum(perceptions.filtered(
            lambda r: r.category_id == categ_g).mapped('total')), 2)
        total_exempt = round(sum(perceptions.filtered(
            lambda r: r.category_id == categ_e).mapped('total')), 2)
        total_salaries = round(sum(perceptions.filtered(
            lambda r: r.salary_rule_id.l10n_mx_edi_code not in [
                '022', '023', '025', '039', '044']).mapped('total')), 2)
        total_compensation = round(sum(perceptions.filtered(
            lambda r: r.salary_rule_id.l10n_mx_edi_code in ['022', '023', '025']).mapped(
                'total')), 2)
        total_retirement = sum(perceptions.filtered(
            lambda r: r.salary_rule_id.l10n_mx_edi_code in ['039', '044']).mapped('total'))
        values = {
            'total_salaries': total_salaries,
            'total_compensation': total_compensation,
            'total_retirement': total_retirement,
            'total_taxed': total_taxed,
            'total_exempt': total_exempt,
            'total_perceptions': (
                total_salaries + total_compensation + total_retirement),
            'category_taxed': categ_g,
            'category_exempt': categ_e,
            'perceptions': perceptions,
        }
        # if the payslip contains only bonus or separation payments,
        # it is of Type "E"
        if (perceptions.filtered(lambda r: r.salary_rule_id.l10n_mx_edi_code in ['002', '023']) and
                not perceptions.filtered(lambda r: r.salary_rule_id.l10n_mx_edi_code in ['001'])):
            values.update({
                'payslip_type': 'E',
            })
        return values

    def get_cfdi_deductions_data(self):
        categ = self.env.ref(
            'l10n_mx_edi_payslip.hr_salary_rule_category_deduction_mx')
        deductions = self.line_ids.filtered(
            lambda r: r.category_id == categ and r.amount)
        total = sum(deductions.mapped('total'))
        total_other = sum(deductions.filtered(
            lambda r: r.salary_rule_id.l10n_mx_edi_code != '002').mapped('total'))
        total_withheld = sum(deductions.filtered(
            lambda r: r.salary_rule_id.l10n_mx_edi_code == '002').mapped('total'))
        return {
            'total_deductions': abs(total),
            'total_other_deductions': abs(total_other),
            'total_taxes_withheld': '%.2f' % abs(total_withheld) if total_withheld else None,  # noqa
            'deductions': deductions,
        }

    def _get_inability_data(self, line):
        # Incapacidad Riesgo de Trabajo
        if line.salary_rule_id == self.env.ref('l10n_mx_edi_payslip.hr_rule_l10n_mx_payroll_deduction_006_irt'):
            days = sum(self.worked_days_line_ids.filtered(lambda w: w.code == 'LEAVE112').mapped('number_of_days'))
            return {'days': days,
                    'inability_type': '01'}
        # Incapacidad Enfermedad General
        if line.salary_rule_id == self.env.ref('l10n_mx_edi_payslip.hr_rule_l10n_mx_payroll_deduction_006'):
            days = sum(self.worked_days_line_ids.filtered(lambda w: w.code == 'LEAVE110').mapped('number_of_days'))
            return {'days': days,
                    'inability_type': '02'}
        # Incapacidad Maternidad
        if line.salary_rule_id == self.env.ref('l10n_mx_edi_payslip.hr_rule_l10n_mx_payroll_deduction_006_im'):
            days = sum(self.worked_days_line_ids.filtered(lambda w: w.code == 'LEAVE111').mapped('number_of_days'))
            return {'days': days,
                    'inability_type': '03'}
        # Licencia para Padres con Hijos con Cancer
        if line.salary_rule_id == self.env.ref('l10n_mx_edi_payslip.hr_rule_l10n_mx_payroll_deduction_006_lphc'):
            days = sum(self.worked_days_line_ids.filtered(lambda w: w.code == 'LEAVE113').mapped('number_of_days'))
            return {'days': days,
                    'inability_type': '04'}
        return {'days': 0,
                'inability_type': ''}

    def get_cfdi_other_payments_data(self):
        """Records with category Other Payments are used in the node
        "OtrosPagos"."""
        categ = self.env.ref(
            'l10n_mx_edi_payslip.hr_salary_rule_category_other_mx')
        other_payments = self.line_ids.filtered(
            lambda r: r.category_id == categ and r.amount)
        return {
            'total_other': abs(sum(other_payments.mapped('total'))),
            'other_payments': other_payments,
        }

    def _l10n_mx_edi_create_cfdi(self):
        """Creates and returns a dictionary containing 'cfdi' if the cfdi is
        well created, 'error' otherwise."""
        self.ensure_one()
        qweb = self.env['ir.qweb']
        error_log = []
        company_id = self.company_id or self.contract_id.company_id
        pac_name = company_id.l10n_mx_edi_pac
        values = self._l10n_mx_edi_create_cfdi_values()

        # -----------------------
        # Check the configuration
        # -----------------------
        # - Check not errors in values generation
        if values.get('error'):
            error_log.append(values.get('error'))

        # -Check certificate
        certificate_ids = company_id.l10n_mx_edi_certificate_ids
        certificate_id = certificate_ids.sudo().get_valid_certificate()
        if not certificate_id:
            error_log.append(_('No valid certificate found'))

        # -Check PAC
        if pac_name:
            pac_test_env = company_id.l10n_mx_edi_pac_test_env
            pac_password = company_id.l10n_mx_edi_pac_password
            if not pac_test_env and not pac_password:
                error_log.append(_('No PAC credentials specified.'))
        else:
            error_log.append(_('No PAC specified.'))

        if error_log:
            return {'error': _(
                'Please check your configuration: ') + create_list_html(
                    error_log)}

        # -----------------------
        # Create the EDI document
        # -----------------------

        # -Compute certificate data
        time_payslip = fields.datetime.strptime(
            self.l10n_mx_edi_time_payslip, DEFAULT_SERVER_TIME_FORMAT).time()
        values['date'] = fields.datetime.combine(
            fields.Datetime.from_string(self.l10n_mx_edi_expedition_date),
            time_payslip).strftime('%Y-%m-%dT%H:%M:%S')
        values['certificate_number'] = certificate_id.serial_number
        values['certificate'] = certificate_id.sudo().get_data()[0]

        # -Compute cfdi
        cfdi = qweb.render(PAYSLIP_TEMPLATE, values=values)

        # -Compute cadena
        tree = self.l10n_mx_edi_get_xml_etree(cfdi)
        cadena = self.l10n_mx_edi_generate_cadena(CFDI_XSLT_CADENA, tree)

        # Post append cadena
        tree.attrib['Sello'] = certificate_id.sudo().get_encrypted_cadena(
            cadena)

        # Check with xsd
        attachment = self.env.ref('l10n_mx_edi.xsd_cached_cfdv33_xsd', False)
        xsd_datas = base64.b64decode(attachment.datas) if attachment else b''
        if xsd_datas:
            try:
                with BytesIO(xsd_datas) as xsd:
                    _check_with_xsd(tree, xsd)
            except (IOError, ValueError):
                _logger.info(_('The xsd file to validate the XML structure '
                               'was not found'))
            except BaseException as e:
                return {'error': (_('The cfdi generated is not valid') +
                                  create_list_html(str(e).split('\\n')))}

        return {'cfdi': etree.tostring(
            tree, pretty_print=True, xml_declaration=True, encoding='UTF-8')}

    def l10n_mx_edi_update_pac_status(self):
        """Synchronize both systems: Odoo & PAC if the payrolls need to be
        signed or cancelled."""
        for record in self:
            if record.l10n_mx_edi_pac_status in ('to_sign', 'retry'):
                record._l10n_mx_edi_retry()
            elif record.l10n_mx_edi_pac_status == 'to_cancel':
                record._l10n_mx_edi_cancel()

    def l10n_mx_edi_update_sat_status(self):
        """Synchronize both systems: Odoo & SAT to make sure the payroll is
        valid."""
        url = 'https://consultaqr.facturaelectronica.sat.gob.mx/ConsultaCFDIService.svc?wsdl'  # noqa
        headers = {'SOAPAction':
                   'http://tempuri.org/IConsultaCFDIService/Consulta',
                   'Content-Type': 'text/xml; charset=utf-8'}
        template = """<?xml version="1.0" encoding="UTF-8"?>
                      <SOAP-ENV:Envelope xmlns:ns0="http://tempuri.org/"
                       xmlns:ns1="http://schemas.xmlsoap.org/soap/envelope/"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
                      <SOAP-ENV:Header/>
                      <ns1:Body>
                      <ns0:Consulta>
                          <ns0:expresionImpresa>?%s</ns0:expresionImpresa>
                      </ns0:Consulta>
                      </ns1:Body>
                      </SOAP-ENV:Envelope>"""
        namespace = {'a': 'http://schemas.datacontract.org/2004/07/'
                     'Sat.Cfdi.Negocio.ConsultaCfdi.Servicio'}
        cfdi_sat_status = {
            'No Encontrado': 'not_found',
            'Cancelado': 'cancelled',
            'Vigente': 'valid',
        }
        for record in self:
            if record.l10n_mx_edi_pac_status not in ['signed', 'cancelled']:
                continue
            supplier_rfc = record.l10n_mx_edi_cfdi_supplier_rfc
            customer_rfc = record.l10n_mx_edi_cfdi_customer_rfc
            total = record.l10n_mx_edi_cfdi_amount
            uuid = record.l10n_mx_edi_cfdi_uuid
            params = url_encode({
                're': supplier_rfc,
                'rr': customer_rfc,
                'tt': total,
                'id': uuid}, separator='&amp;')
            soap_env = template % (params)
            try:
                soap_xml = requests.post(url, data=soap_env, headers=headers)
                response = objectify.fromstring(soap_xml.text)
                status = response.xpath('//a:Estado', namespaces=namespace)
            except BaseException as e:  # pragma: no cover
                record.l10n_mx_edi_log_error(str(e) or e.reason.__repr__())  # noqa pragma: no cover
                continue  # pragma: no cover
            record.l10n_mx_edi_sat_status = cfdi_sat_status.get(
                status[0] if status else False, 'none')

    def _get_worked_day_lines(self):
        """Overwrite WORK100 to get all days in the period"""
        result = super(HrPayslip, self)._get_worked_day_lines()
        result = self._set_leaves_calendar_days_count(result)
        hours_per_day = result[0]['number_of_hours'] / result[0]['number_of_days'] if (
            result and result[0]['number_of_days'] != 0) else 0
        total = sum([line['number_of_days'] for line in result])
        work_entry = self.env.ref('hr_work_entry.work_entry_type_attendance')
        out_contract = self.env.ref('l10n_mx_edi_payslip.hr_work_entry_type_out_of_contract')
        date_from = max(self.date_from, self.contract_id.date_start)
        days = self.contract_id.get_seniority(date_from, self.date_to, 'a')['days']
        days_out_start, days_out_end = self._get_out_of_contract_days()
        total -= sum([line['number_of_days'] for line in result if line['work_entry_type_id'] == out_contract.id])
        # Adjust Attendances
        for line in result:
            if line['work_entry_type_id'] == work_entry.id:
                line['number_of_days'] = line['number_of_days'] + days - total - days_out_end

        # Include Out of contract line
        out_of_contract_days = days_out_start + days_out_end
        if out_of_contract_days:
            result.append({
                'sequence': out_contract.sequence,
                'work_entry_type_id': out_contract.id,
                'number_of_days': out_of_contract_days,
                'number_of_hours': hours_per_day * out_of_contract_days,
                'amount': 0
            })

        # Check there are all days in the period, refill with attendences if not
        payslip_period_days = (self.date_to - self.date_from).days + 1
        worked_days = sum([line['number_of_days'] for line in result])
        if worked_days < payslip_period_days and result:
            days = payslip_period_days - worked_days
            result.append({
                'sequence': work_entry.sequence,
                'work_entry_type_id': work_entry.id,
                'number_of_days': days,
                'number_of_hours': hours_per_day * days,
                'amount': 0,
            })

        # Adjust amounts after refilling worked days
        total_amount = sum([line['amount'] for line in result if line.get('amount')])
        total_hours = sum([line['number_of_days'] for line in result])
        for line in result:
            line['amount'] = line['number_of_days'] * total_amount / total_hours
        return result

    def _get_out_of_contract_days(self):
        """If the contract doesn't cover the whole payslip period, get how many days are out of contract period"""
        contract = self.contract_id
        if not contract:
            return 0, 0
        days_out_start = (contract.date_start - self.date_from).days if contract.date_start > self.date_from else 0
        days_out_end = 0 if not contract.date_end or contract.date_end >= self.date_to else (
            self.date_to - contract.date_end).days
        return days_out_start, days_out_end

    def _set_leaves_calendar_days_count(self, worked_day_lines):
        """This method sets on the worked_day_lines the missing days that are out of normal employee's work schedule
        in the period of hr.leaves that uses calendar days

        - Get which days the employee does not work being 0 Monday and 6 Sunday
        - Get week days that normally the employee does not work
        - Get the specific dates when the employee does not work in the payslip period
        - for each date, search if there is at least one hr.leave that:
            Uses calendar days
            The date is beetween leave period
            Is for the payslip employee
        If there is at least one, count a day, save the count grouping by hr.leave hr.work.entry.type
        - For each group, check in worked_day_lines. If there is a dict with work_entry_type_id set,
        add the days count to its number_of_days and number_of_hours. If not, create a new dict in the
        worked_day_lines list to create a new worked day on the payslip.
        """
        work_days = self.contract_id.resource_calendar_id.attendance_ids.mapped('dayofweek')
        not_work_days = list(set(['0', '1', '2', '3', '4', '5', '6']) - set(work_days))

        leave_days = {}
        for day in range((self.date_to - self.date_from).days + 1):
            date = self.date_from + timedelta(days=day)
            if str(date.weekday()) not in not_work_days:
                continue
            leave = self.env['hr.leave'].search([
                ('holiday_status_id.l10n_mx_edi_payslip_use_calendar_days', '=', True),
                ('employee_id', '=', self.employee_id.id),
                ('state', '=', 'validate'),
                ('date_from', '<', fields.datetime.combine(date, dt_time(0))),
                ('date_to', '>', fields.datetime.combine(date, dt_time(0))),
            ], limit=1)
            if not leave:
                continue
            # Use entry type as key and count as value
            # If the entry type is already set, sum 1, if not set the count as 1
            entry_type_id = leave.holiday_status_id.work_entry_type_id.id
            leave_days[entry_type_id] = leave_days[entry_type_id] + 1 if leave_days.get(entry_type_id) else 1

        # Add the work entry type and count to the result/worked_day_lines dict
        for work_entry_type, days_count in leave_days.items():
            is_entry_set = False
            for line in worked_day_lines:
                if line['work_entry_type_id'] == work_entry_type:
                    line['number_of_days'] = line['number_of_days'] + days_count
                    line['number_of_hours'] = line['number_of_hours'] + days_count * 8
                    is_entry_set = True
                    break

            if is_entry_set:
                continue
            worked_day_lines.append({
                'sequence': 25,
                'work_entry_type_id': work_entry_type,
                'number_of_days': days_count,
                'number_of_hours': 8.0 * days_count
            })
        return worked_day_lines

    def l10n_mx_edi_is_last_payslip(self):
        """Check if the date to in the payslip is the last of the current month
        and return True in that case, to know that is the last payslip"""
        if not self:
            return False
        self.ensure_one()
        if not self.date_to:
            return False
        # Case for biweekly
        if self.date_to.day == monthrange(self.date_to.year, self.date_to.month)[1]:
            return True
        # projection for the next slips
        dbtw = abs((self.date_to - self.date_from).days) + 1
        next_date = self.date_to + timedelta(days=dbtw)
        if self.date_from.month != self.date_to.month and self.date_from.month != next_date.month:
            return True
        return False

    def l10n_mx_edi_name(self, payslip_line):
        self.ensure_one()
        if not self.company_id.l10n_mx_edi_dynamic_name:
            return payslip_line.name
        # Getting salary rule code on input code form, to know if this payslip line has input lines.
        code = payslip_line.salary_rule_id.code
        code = '%s_%s' % (code[:2].lower(), code[2:])
        inputs = self.input_line_ids.filtered(lambda l, code=code: l.code == code)

        if not inputs:
            return payslip_line.name

        details = self.env['hr.payslip.extra.detail'].search([
            ('employee_id', '=', self.employee_id.id),
            ('extra_id.state', '=', 'approved'),
            ('extra_id.date', '>=', self.date_from),
            ('extra_id.date', '<=', self.date_to),
            ('extra_id.input_id', 'in', inputs.input_type_id.ids),
        ])
        if details and details.filtered('detail'):
            return '%s: %s' % (payslip_line.name, ', '.join(details.mapped('detail')))

        return payslip_line.name

    def l10n_mx_edi_update_extras(self):
        """Update the extra inputs defined for the employees"""
        if self:
            extras = self.env['hr.payslip.extra'].search([
                ('state', '=', 'approved'),
                ('date', '>=', self.mapped('payslip_run_id').date_start or self[0].date_from),
                ('date', '<=', self.mapped('payslip_run_id').date_end or self[0].date_to)])
            for slip in self.filtered('contract_id'):
                slip_extras = extras.mapped('detail_ids').filtered(
                    lambda e: e.employee_id == slip.employee_id and e.amount)
                slip.input_line_ids.filtered(lambda l: l.code in slip_extras.mapped(
                    'extra_id.input_id.code')).unlink()
                for extra, _records in groupby(slip_extras, lambda r: r.extra_id):
                    slip.input_line_ids = [(0, 0, {
                        'amount': sum(slip_extras.filtered(lambda e: e.extra_id == extra).mapped('amount')),
                        'code': extra.input_id.code,
                        'contract_id': slip.contract_id.id,
                        'input_type_id': extra.input_id.id,
                    })]
                slip.compute_sheet()

    def _get_dates_on_datetime(self, timezone=None):
        """Cast payslips dates to datetime considering time zone. Used to compare dates on salary rules."""
        tz = timezone or pytz_timezone(self.employee_id.tz or self.env.user.tz)
        # Creating dates with Timezone, 'imitating' odoo behavior.
        date_from = fields.datetime.combine(self.date_from, dt_time(0, 0), tz)
        date_to = fields.datetime.combine(self.date_to, dt_time(23, 59, 59), tz)
        # Storing datetime equivalent in UTC. 'Imitating' odoo
        date_from = date_from.astimezone()
        date_to = date_to.astimezone()
        # Removing tzinfo. datetime with tzinfo can't be used to compare, the values are not affected.
        date_from = date_from.replace(tzinfo=None)
        date_to = date_to.replace(tzinfo=None)
        return date_from, date_to

    def _get_attendances(self):
        """Get the attendances of the employee in the period of payslip,
        return Attendances where check_in is between payslips dates, date_from and date_to
        Using the employee timezone or user timezone
        If the module Attendances is not installed return an empty list."""
        if not self:
            return []
        # Cast payslip dates to datetime to be avaliable to compare on the filtered
        date_from, date_to = self._get_dates_on_datetime()
        attendances = self.employee_id.attendance_ids.filtered(
            lambda att: att.check_in >= date_from and att.check_in <= date_to)
        return attendances

    def _get_attendances_weekdays(self):
        """ Get a list of worked days gotten from attendances
        Days converted considering timezone
        return weekdays represented by int. Monday as 0, sunday as 6.
        If the module Attendances is not installed return an empty list."""
        attendances = self._get_attendances()
        tz = pytz_timezone(self.employee_id.tz or self.env.user.tz)
        days = []
        for attendance in attendances:
            date = attendance.check_in.astimezone(tz)
            days.append(date.weekday())
        return days

    def auto_generate_overtimes(self):
        overtime = self.env['hr.payslip.overtime']
        for record in self:
            for day in range((record.date_to - record.date_from).days + 1):
                date = record.date_from + timedelta(days=day)
                if overtime.search_count([('name', '=', date), ('employee_id', '=', record.employee_id.id)]):
                    continue
                overtime.create({
                    'name': record.date_from + timedelta(days=day),
                    'employee_id': record.employee_id.id,
                })

    def get_overtime_data(self, is_simple=False):
        """Get the overtimes for the salary rule, if receive is_simple will to search the overtimes with that check"""
        self.ensure_one()
        overtimes = self.env['hr.payslip.overtime'].search([
            ('employee_id', '=', self.employee_id.id),
            ('name', '>=', self.date_from),
            ('name', '<=', self.date_to),
            ('hours', '!=', 0),
            ('is_simple', '=', is_simple)
        ])
        if not overtimes:
            return {}
        detail = {}
        weeks_overtimes = overtimes.search([
            ('employee_id', '=', self.employee_id.id),
            ('week', 'in', overtimes.mapped('week')),
            ('hours', '!=', 0),
        ])
        for overtime in weeks_overtimes.sorted('name'):
            if overtime.week not in detail:
                detail[overtime.week] = {'paid': 0, 'no_paid': 0}
            if overtime.id not in overtimes.ids:
                detail[overtime.week]['paid'] = detail[overtime.week]['paid'] + overtime.hours
                continue
            detail[overtime.week]['no_paid'] = detail[overtime.week]['no_paid'] + overtime.hours
        return detail

    def action_open_overtimes(self):
        self.ensure_one()
        self.auto_generate_overtimes()
        weeks = []
        for day in range((self.date_to - self.date_from).days + 1):
            weeks.append((self.date_from + timedelta(days=day)).isocalendar()[1])
        return {
            'name': _('Overtimes'),
            'view_mode': 'tree,form',
            'res_model': 'hr.payslip.overtime',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [
                ('employee_id', '=', self.employee_id.id),
                ('week', 'in', weeks),
            ],
        }

    def _get_inability_bonus(self, only_days=False):
        """If only_days, return the leave days that must be paid in this payslip as inability"""
        contract = self.contract_id
        leave = self.env.ref('hr_payroll.work_entry_type_sick_leave')
        domain = [('work_entry_type_id', '=', leave.id)]
        work_entry = self.env['hr.work.entry'].search(
            contract._get_work_hours_domain(self.date_from, self.date_to, domain=domain, inside=True))
        payment_daily = (contract.wage / 30)
        result = 0
        for leave in work_entry.mapped('leave_id'):
            days = number_of_days = 0
            for day in range(3 if leave.number_of_days >= 3 else int(leave.number_of_days)):
                if (leave.date_from + timedelta(days=day)).date() >= self.date_from and (
                        leave.date_from + timedelta(days=day)).date() <= self.date_to:
                    days += 1
            if only_days:
                return days
            for day in range((self.date_to - self.date_from).days + 1):
                date = self.date_from + timedelta(days=day)
                if leave.date_from.date() <= date <= leave.date_to.date():
                    number_of_days += 1
            if number_of_days > days > 3:
                result += (payment_daily - (contract.l10n_mx_edi_sbc * .60)) * (number_of_days - days)
        return result

    def _get_full_leaves(self, code):
        if not self:
            return 0
        count = 0
        date = self.date_from
        for _day in range((self.date_to - self.date_from).days + 1):
            date = date + timedelta(days=1)
            if self.env['hr.leave'].search([
                    ('holiday_status_id.work_entry_type_id.code', '=', code),
                    ('state', '=', 'validate'),
                    ('employee_id', '=', self.employee_id.id),
                    ('date_from', '<=', date),
                    ('date_to', '>=', date)], limit=1):
                count += 1
        return count


class HrPayslipOvertime(models.Model):
    _name = 'hr.payslip.overtime'
    _description = 'Pay Slip overtime'
    _order = 'name'

    name = fields.Date(
        'Date', help='Indicate the date for the overtime', required=True)
    payslip_id = fields.Many2one(
        'hr.payslip', ondelete='cascade', help='Payslip related.')
    hours = fields.Integer(
        help="Number of overtime hours worked in the period")
    is_simple = fields.Boolean(
        help="Indicate if this overtime must be paid like simple.")
    employee_id = fields.Many2one(
        'hr.employee', help='Indicate the employee to this overtime.')
    week = fields.Integer(
        compute='_compute_overtime_week', store=True,
        help='Saves the week number to compute the exempt amount.')

    @api.depends('name')
    def _compute_overtime_week(self):
        for record in self:
            record.week = record.name.isocalendar()[1] if record.name else False

    def unlink(self):
        if self.filtered(lambda o: o.payslip_id.state == 'done'):
            raise UserError(_("You cannot delete an overtime which payroll has been posted once."))
        return super(HrPayslipOvertime, self).unlink()


class HrPayslipActionTitles(models.Model):
    _name = 'hr.payslip.action.titles'
    _description = 'Pay Slip action titles'

    payslip_id = fields.Many2one(
        'hr.payslip', required=True, ondelete='cascade',
        help='Payslip related.')
    category_id = fields.Many2one(
        'hr.salary.rule.category', 'Category', required=True,
        help='Indicate to which perception will be added this attributes in '
        'node XML')
    market_value = fields.Float(
        help='When perception type is 045 this value must be assigned in the '
        'line. Will be used in node "AccionesOTitulos" to the attribute '
        '"ValorMercado"', required=True)
    price_granted = fields.Float(
        help='When perception type is 045 this value must be assigned in the '
        'line. Will be used in node "AccionesOTitulos" to the attribute '
        '"PrecioAlOtorgarse"', required=True)


class HrPayslipExtraPerception(models.Model):
    _name = 'hr.payslip.extra.perception'
    _description = 'Pay Slip extra perception'

    payslip_id = fields.Many2one(
        'hr.payslip', required=True, ondelete='cascade',
        help='Payslip related.')
    node = fields.Selection(
        [('retirement', 'JubilacionPensionRetiro'),
         ('separation', 'SeparacionIndemnizacion')], help='Indicate what is '
        'the record purpose, if will be used to add in node '
        '"JubilacionPensionRetiro" or in "SeparacionIndemnizacion"')
    amount_total = fields.Float(
        help='If will be used in the node "JubilacionPensionRetiro" and '
        'will be used to one perception with code "039", will be used to '
        'the attribute "TotalUnaExhibicion", if will be used to one '
        'perception with code "044", will be used to the attribute '
        '"TotalParcialidad". If will be used in the node '
        '"SeparacionIndemnizacion" will be used in attribute "TotalPagado"')
    amount_daily = fields.Float(
        help='Used when will be added in node "JubilacionPensionRetiro", to '
        'be used in attribute "MontoDiario"')
    accumulable_income = fields.Float(
        help='Used to both nodes, each record must be have the valor to each '
        'one.')
    non_accumulable_income = fields.Float(
        help='Used to both nodes, each record must be have the valor to each '
        'one.')
    service_years = fields.Integer(
        help='Used when will be added in node "SeparacionIndemnizacion", to '
        'be used in attribute "NumAñosServicio"')
    last_salary = fields.Float(
        help='Used when will be added in node "SeparacionIndemnizacion", to '
        'be used in attribute "UltimoSueldoMensOrd"')


class HrPayslipRun(models.Model):
    _name = 'hr.payslip.run'
    _inherit = ['hr.payslip.run', 'mail.thread', 'mail.activity.mixin']

    l10n_mx_edi_payment_date = fields.Date(
        'Payment Date', required=True,
        default=time.strftime('%Y-%m-01'), help='Save the payment date that '
        'will be added on all payslip created with this batch.')
    l10n_mx_edi_productivity_bonus = fields.Float(
        'Productivity Bonus', help='The amount to distribute to the employees in the payslips.')

    def action_payslips_done(self):
        self.ensure_one()
        if not self.user_has_groups('l10n_mx_edi_payslip.allow_validate_payslip'):
            raise UserError(_(
                "Only Managers who are allow to Validate payslip can perform this operation"))
        # using search instead of filtered to keep performance in batch with many payslips  # noqa
        payslips = self.slip_ids.search(
            [('id', 'in', self.slip_ids.ids), ('state', '=', 'draft')])
        for payslip in payslips:
            try:
                with self.env.cr.savepoint():
                    payslip.action_payslip_done()
            except UserError as e:
                payslip.message_post(
                    body=_('Error during the process: %s') % e)
        retry_payslips = (self.slip_ids - payslips).filtered(
            lambda r: r.l10n_mx_edi_pac_status in [
                'retry', 'to_sign', 'to_cancel'])
        retry_payslips.l10n_mx_edi_update_pac_status()

    def action_payroll_sent(self):
        """Send email for all signed payslips"""
        self.ensure_one()
        template = self.env.ref(
            'l10n_mx_edi_payslip.email_template_edi_payroll', False)
        mail_composition = self.env['mail.compose.message']
        for payslip in self.slip_ids.filtered(
            lambda p: (p.state == 'done' and not p.sent and
                       p.l10n_mx_edi_pac_status == 'signed' and
                       p.employee_id.work_email)):
            res = mail_composition.create({
                'model': 'hr.payslip',
                'res_id': payslip.id,
                'template_id': template and template.id or False,
                'composition_mode': 'comment'})
            res.onchange_template_id_wrapper()
            mail_composition |= res
        # send all
        mail_composition.action_send_mail()

    def action_print_payroll_dispersion(self):
        self.ensure_one()
        if not self.env.user.has_group('l10n_mx_edi_payslip.l10n_mx_edi_allow_print_payslip_dispertion'):
            raise UserError(_("Only Managers with the group 'Allow to Print Payslip Dispersion' can generate "
                              "payslip dispersion files"))

        ids = {'list_ids': ','.join(str(x) for x in self.ids)}
        return {
            'name': 'PayslipDispersion',
            'type': 'ir.actions.act_url',
            'url': '/print/payslip/dispersions?list_ids=%(list_ids)s' % ids,
        }

    def _get_payslips_dispersions(self):
        """Get the payslip dispersions, 1 for each bank on payslip batch
        :return: List of tuples, 2 values. Report name and text
        :rtype: list"""
        if not self.env.user.has_group('l10n_mx_edi_payslip.l10n_mx_edi_allow_print_payslip_dispertion'):
            raise UserError(_("Only Managers with the group 'Allow to Print Payslip Dispersion' can generate "
                              "payslip dispersion files"))
        dispersions = []
        bank_errors = []

        for bank_id in self.mapped('slip_ids.employee_id.bank_account_id.bank_id'):
            # using search instead filtered to keep performance in batch with many payslips like action_payslips_done()
            payslips = self.slip_ids.search([
                ('id', 'in', self.slip_ids.ids),
                ('employee_id.bank_account_id.bank_id', '=', bank_id.id)
            ])
            # Call generate dispersion methods with the firts word of the bank name
            # The method must return lines prepered by _prepare_join_dispersion_lines
            bank_func = '_generate_%s_dispersion' % bank_id.name.split(' ')[0].lower()
            try:
                text = getattr(self, bank_func)(payslips)
            except AttributeError:
                bank_errors.append(bank_id.name)
                continue
            file_name = self._get_payslips_dispersion_report_name(bank_id.name)
            dispersions.append((file_name, text))

        if bank_errors:
            body_msg = _("The following of your banks are not available for payroll dispersion")
            self.message_post(body=body_msg + create_list_html(bank_errors))

        return dispersions

    @api.model
    def _generate_bbva_dispersion(self, payslips):
        """According to BBVA documentation, Gotten from BBVA portal."""
        lines = []
        for index, payslip in enumerate(payslips):
            consecutive = str(index + 1).zfill(9).ljust(25)
            bank_account = payslip.employee_id.bank_account_id.acc_number
            bank_account = str(bank_account).ljust(20)
            amount = payslip.line_ids.filtered(lambda s: s.code == "NetSalary").total
            amount = str(amount).replace('.', '').zfill(15)
            employee_name = payslip.employee_id.name.ljust(40)[:40]
            # 001 are fixed values, represent bank and branch. 99 Account type
            line = "%s%s%s%s%s%s%s" % (consecutive, "99", bank_account, amount, employee_name, '001', '001')
            lines.append(line)
        return self._prepare_join_dispersion_lines(lines)

    @api.model
    def _generate_santander_dispersion(self, slips):
        """For now Dummny method, shows how other banks methods will be structured, replace this docstring
           when santander is supported, this methods must return the lines prepared by the methos
           _prepare_join_dispersion_lines()"""
        return self._generate_bbva_dispersion(slips)

    @api.model
    def _prepare_join_dispersion_lines(self, lines):
        return '\r\n'.join(lines) + "\r\n"

    @api.model
    def _get_payslips_dispersion_report_name(self, bank_name=False):
        self.ensure_one()
        name = self.name.replace(' ', '_')
        bank_name = bank_name.replace(' ', '_') if bank_name else _('Dispersions')
        date = self.l10n_mx_edi_payment_date.strftime("%d_%m_%Y")
        return '%s_%s_%s' % (bank_name, date, name)


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    journal_item_ids = fields.Many2many('account.move.line', string="Journal Items",
                                        help="Journal items created by this payslip line when was validated.")
    l10n_mx_edi_schedule_pay = fields.Selection(related='contract_id.l10n_mx_edi_schedule_pay', store=True)
