from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    validated_invoice_id = fields.Many2one(
        'account.invoice', 
        string='Validated by Invoice', 
        help='The invoice that validated this picking and set it to done.'
    )


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    # Campo Many2one que relaciona la factura con el pedido de venta
    sale_order_id = fields.Many2one('sale.order', string="Pedido de Venta Relacionado", readonly=True)
    
    # Campo que relaciona la factura con el picking que la validó
    validated_picking_id = fields.Many2one(
        'stock.picking', 
        string='Validated Picking', 
        help='The picking that validated this invoice.'
    )

    @api.model
    def create(self, vals):
        # Crear la factura
        invoice = super(AccountInvoice, self).create(vals)

        # Verificar si se ha proporcionado un valor para 'origin'
        if vals.get('origin'):
            # Buscar el pedido de venta relacionado
            sale_order = self.env['sale.order'].search([('name', '=', vals['origin'])], limit=1)
            if sale_order:
                invoice.sale_order_id = sale_order.id
            else:
                # Registrar un mensaje si no se encuentra el pedido de venta
                _logger.warning(f"No se encontró un pedido de venta con el nombre '{vals['origin']}'")

        return invoice



class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_open(self):
        # Llama al método original para validar la factura
        res = super(AccountInvoice, self).action_invoice_open()

        for invoice in self:
            if invoice.sale_order_id:
                sale_order = invoice.sale_order_id
                for picking in sale_order.picking_ids.filtered(lambda p: p.state in ['confirmed', 'assigned']):
                    for move_line in picking.move_line_ids:
                        invoice_line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == move_line.product_id)
                        if invoice_line:
                            # Obtener la cantidad disponible reservada desde el movimiento principal (move_id)
                            qty_reserved = move_line.move_id.reserved_availability
                            qty_to_process = sum(line.quantity for line in invoice_line)

                            if qty_reserved > 0:
                                # Procesar solo hasta la cantidad reservada o la cantidad requerida
                                move_line.qty_done = min(qty_reserved, qty_to_process)

                    # Validar el picking si todas las líneas procesadas tienen cantidades completas
                    pending_lines = picking.move_line_ids.filtered(lambda ml: ml.qty_done < ml.product_uom_qty)
                    if not pending_lines:
                        picking.validated_invoice_id = invoice
                        picking.sudo().action_done()
                        invoice.validated_picking_id = picking
                        invoice.message_post(body=_("Todos los movimientos de inventario relacionados al pedido %s han sido confirmados y procesados según la factura.") % sale_order.name)
                    else:
                        invoice.message_post(body=_("Algunas líneas de productos en el picking del pedido %s no tienen disponibilidad completa.") % sale_order.name)

        return res
