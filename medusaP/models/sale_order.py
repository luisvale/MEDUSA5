from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    validated_invoice_id = fields.Many2one(
        'account.invoice',
        string='Validated by Invoice',
        help='The invoice that validated this picking and set it to done.'
    )


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    # Campo Many2one para relacionar el picking que validó la factura
    validated_picking_id = fields.Many2one(
        'stock.picking',
        string='Validated Picking',
        help='Picking relacionado que validó esta factura'
    )

    # Campo Many2one que relaciona la factura con el pedido de venta
    sale_order_id = fields.Many2one(
        'sale.order',
        string="Pedido de Venta Relacionado",
        readonly=True
    )

    @api.model
    def create(self, vals):
        """ Sobrecarga del método create para asignar el pedido de venta relacionado """
        invoice = super(AccountInvoice, self).create(vals)

        if vals.get('origin'):
            sale_order = self.env['sale.order'].search([('name', '=', vals['origin'])], limit=1)
            if sale_order:
                invoice.sale_order_id = sale_order.id
            else:
                _logger.warning("No se encontró un pedido de venta con el nombre '%s'", vals['origin'])

        return invoice

    @api.multi
    def action_invoice_open(self):
        """ Sobrecarga de action_invoice_open para procesar los movimientos de inventario relacionados """
        res = super(AccountInvoice, self).action_invoice_open()

        for invoice in self:
            if invoice.sale_order_id:
                sale_order = invoice.sale_order_id

                # Procesar los pickings relacionados con el pedido de venta
                for picking in sale_order.picking_ids.filtered(lambda p: p.state in ['confirmed', 'assigned']):
                    for move_line in picking.move_line_ids:
                        # Buscar la línea de factura correspondiente al producto del movimiento
                        invoice_line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == move_line.product_id)
                        if invoice_line:
                            # Calcular la cantidad a procesar
                            qty_reserved = move_line.move_id.reserved_availability
                            qty_to_process = sum(line.quantity for line in invoice_line)

                            if qty_reserved > 0:
                                # Procesar solo hasta la cantidad reservada o la cantidad requerida
                                move_line.qty_done = min(qty_reserved, qty_to_process)

                    # Validar el picking si no hay líneas pendientes
                    pending_lines = picking.move_line_ids.filtered(lambda ml: ml.qty_done < ml.product_uom_qty)
                    if not pending_lines:
                        picking.validated_invoice_id = invoice.id
                        picking.sudo().action_done()

                        # Actualizar la relación entre el picking y la factura
                        invoice.validated_picking_id = picking.id
                        invoice.message_post(
                            body=_("Todos los movimientos de inventario relacionados al pedido %s han sido confirmados y procesados según la factura.") % sale_order.name
                        )
                    else:
                        invoice.message_post(
                            body=_("Algunas líneas de productos en el picking del pedido %s no tienen disponibilidad completa.") % sale_order.name
                        )

        return res