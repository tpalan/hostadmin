from pprint import pprint

from odoo import models, fields, api
import datetime


class AccountInvoiceLine(models.Model):
    _inherit = 'account.move.line'
    hostadmin_billing_id = fields.Many2one('hostadmin.billing', required=False)


class HostadminBilling(models.Model):
    _name = 'hostadmin.billing'
    _description = 'Verrechnung'
    invoice_line = fields.Many2one('account.move.line', string='Rechnungsposition', required=False,
                                   ondelete='cascade')
    period_start = fields.Date('Start Periode', required=True)
    period_end = fields.Date('Ende Periode', required=True)
    hosting_id = fields.Many2one('hostadmin.hosting')


class HostadminHosting(models.Model):
    _name = 'hostadmin.hosting'
    _description = 'Hosting'
    billing_date = fields.Date('Start Abrechnung', required=True)
    next_billing_date = fields.Date('Nächste Verrechnung', compute='_compute_next_billing',
                                    help="Automatisch berechnet aus Start Abrechnung +1 Jahr und schon erstellten Rechnungen")
    product_id = fields.Many2one('product.product', string='Tarif', ondelete='restrict', required=True)
    domain_id = fields.Many2one('hostadmin.domain', string='Domain reference', index=True)
    price = fields.Monetary('Spezialtarif',
                            help="Auf einen Wert ungleich 0 setzen um den Spezialtarif statt dem Listenpreis zu benutzen")
    list_price = fields.Float('Listenpreis', related='product_id.list_price', digits='Product Price',
                              readonly=True, help="Listenpreis aus Produkt")
    #	price = fields.Monetary('Tarif')
    currency_id = fields.Many2one('res.currency', related='domain_id.currency_id')

    @api.depends('billing_date')
    def _compute_next_billing(self):
        billing_obj = self.env['hostadmin.billing']
        for record in self:
            # iterate through billings and calculate the next billing date
            if not record.billing_date:
                record.next_billing_date = None
                continue
            billing_date = record.billing_date
            next_billing = billing_date
            found = False
            while found == False:
                # print "while"
                billed = False
                for billing in billing_obj.search([('hosting_id', '=', record.id)]):
                    if not billing.period_start:
                        continue
                    if not billing.period_end:
                        continue

                    p_start = billing.period_start
                    p_end = billing.period_end
                    # check if next_billing is between these two
                    if (p_start <= next_billing <= p_end):
                        billed = True
                        break
                if (billed):
                    next_billing = next_billing.replace(year=next_billing.year + 1)
                else:
                    found = True
            record.next_billing_date = next_billing


class HostadminDomain(models.Model):
    _name = 'hostadmin.domain'
    _description = 'Domain'
    _order = "name"
    name = fields.Char('Domainname', index=True, required=True)
    customer_id = fields.Many2one('res.partner', string="Endkunde", required=True)
    admin = fields.Many2one('res.users', string="Bearbeiter")
    hoster = fields.Many2one('res.partner', string="Hoster")
    hostings = fields.One2many('hostadmin.hosting', 'domain_id', string='Hosting-Tarife')
    next_billing_date = fields.Date('Nächste Verrechnung', compute='_compute_next_billing')
    currency_id = fields.Many2one('res.currency')

    @api.depends('hostings')
    def _compute_next_billing(self):
        for record in self:
            next_billing = datetime.datetime.now().date()
            next_billing = next_billing.replace(year=next_billing.year + 10)
            found = False
            for hosting in record.hostings:
                h_next_billing = hosting.next_billing_date
                if h_next_billing < next_billing:
                    found = True
                    next_billing = h_next_billing
            if found == True:
                record.next_billing_date = next_billing
            else:
                record.next_billing_date = None

    def _prepare_invoice(self, domain):

        # self.ensure_one()
        # self = self.with_context(default_company_id=domain.customer_id.company_id.id,
        #                         force_company=domain.customer_id.company_id.id)
        # journal = self.env['account.move'].with_context(default_type='out_invoice')._get_default_journal()
        # if not journal:
        #    raise UserError(_('Please define an accounting sales journal for the company'))

        # get last day of month
        now = datetime.datetime.now()
        # invoice_date = datetime.date(now.year, now.month, calendar.monthrange(now.year, now.month)[1])
        invoice_vals = {
            # 'ref': '',
            'type': 'out_invoice',
            # 'ref': 'Domain/Hostinggebühren',
            'partner_id': domain.customer_id.id,
            # 'state': 'draft',
            # 'company_id': domain.customer_id.company_id.id,
            # 'journal_id': journal.id,  # company comes from the journal
            # 'user_id': domain.customer_id.user_id.id,
            # 'transaction_ids': [(6, 0, self.transaction_ids.ids)],
            'invoice_line_ids': [],
            # 'date_invoice': invoice_date,
        }
        return invoice_vals

    def generate_invoice(self):
        account_revenue = self.env['account.account'].search(
            [('user_type_id', '=', self.env.ref('account.data_account_type_revenue').id)], limit=1)

        lang_obj = self.env['res.lang']

        inv_map = {}
        bdate_map = {}
        edate_map = {}

        for domain in self:

            customer_id = domain.customer_id.id
            domainName = domain.name
            lang_ids = lang_obj.search([('code', '=', domain.customer_id.lang)])
            lang = lang_ids[0]

            next_billing = domain.next_billing_date
            now = datetime.datetime.now().date()
            if next_billing <= now:
                # we need to create an invoice for this customer, look if we have already
                # invoice_vals = None
                invoice = None
                if customer_id in inv_map:
                    # invoice = inv_map[customer_id]
                    invoice_vals = inv_map[customer_id]
                else:
                    invoice_vals = self._prepare_invoice(domain)
                    # invoice = self.env['account.move'].create(invoice_vals)
                    inv_map[customer_id] = invoice_vals
                    # inv_map[customer_id] = invoice
                    bdate_map[customer_id] = next_billing
                    edate_map[customer_id] = next_billing

                # for every hosting that should be billed: generate an invoice-line
                for hosting in domain.hostings:
                    h_next_billing = hosting.next_billing_date
                    period_end = h_next_billing.replace(year=h_next_billing.year + 1)

                    # subtract one day from period-end
                    period_end -= datetime.timedelta(days=1)

                    if h_next_billing <= now:

                        if bdate_map[customer_id] > h_next_billing:
                            bdate_map[customer_id] = h_next_billing
                        if edate_map[customer_id] < period_end:
                            edate_map[customer_id] = period_end

                        price = hosting.product_id.list_price
                        if hosting.price > 0:
                            price = hosting.price

                        # create a billings object to note billing
                        billing_object = self.env['hostadmin.billing'].create({
                            'period_start': h_next_billing,
                            'period_end': period_end,
                            'hosting_id': hosting.id,
                        })

                        uom = hosting.product_id.uom_id.id
                        product_name = hosting.product_id.name
                        invoice_line_vals = {
                            # 'display_type': self.display_type,
                            # 'sequence': self.sequence,
                            # 'tax_ids': [(6, 0, self.tax_id.ids)],
                            # 'analytic_account_id': self.order_id.analytic_account_id.id,
                            # 'analytic_tag_ids': [(6, 0, hosting.product_id.prself.analytic_tag_ids.ids)],
                            # 'sale_line_ids': [(4, self.id)],
                            'price_unit': price,
                            'product_id': hosting.product_id.id,
                            'quantity': 1,
                            # 'discount': 0.0,
                            # 'move_id': invoice.id,
                            'name': product_name + "\nDomain: " + domainName + " (" + h_next_billing.strftime(
                                lang.date_format) + " bis " + period_end.strftime(lang.date_format) + ")",
                            # 'account_id': account_revenue.id,
                            'tax_ids': [(6, 0, hosting.product_id.taxes_id.ids)],
                            'product_uom_id': uom,
                            'hostadmin_billing_id': billing_object.id
                        }

                        invoice_vals['invoice_line_ids'].append((0, None, invoice_line_vals))
                        # invoice_line = self.env['account.move.line'].create(invoice_line_vals)

                        # update invoice "Leistungszeitraum"
                        date1 = bdate_map[customer_id]
                        date2 = edate_map[customer_id]
                        invoice_vals['period'] = date1.strftime("%m/%y") + "-" + date2.strftime("%m/%y")
                        # invoice['period'] = date1.strftime("%m/%y") + "-" + date2.strftime("%m/%y")
                        inv_map[customer_id] = invoice_vals
                        # inv_map[customer_id] = invoice

        invoice_vals_list = []
        for invoice_vals in inv_map.values():
            invoice_vals_list.append(invoice_vals)
        pprint(invoice_vals_list)
        invoices = self.env['account.move'].create(invoice_vals_list)
        # relink hostadmin billing objects
        for invoice in invoices:
            for invoice_line in invoice.invoice_line_ids:
                billing_object = invoice_line.hostadmin_billing_id
                billing_object.invoice_line = invoice_line.id
