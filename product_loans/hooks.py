from odoo import api, SUPERUSER_ID

def post_install_hook(env):
    """Hook ejecutado después de la instalación del módulo (Odoo 18: recibe env)."""
    cr = env.cr
    registry = env.registry

    # 1) Crear configuración contable por compañía si el modelo existe
    LoanAccountingManager = registry.get('loan.accounting.manager')
    if LoanAccountingManager:
        su_env = api.Environment(cr, SUPERUSER_ID, {})
        Company = su_env['res.company']
        Config = su_env['loan.accounting.manager']

        for company in Company.search([]):
            exists = Config.search([('company_id', '=', company.id)], limit=1)
            if not exists:
                try:
                    Config.create({'company_id': company.id})
                except Exception as e:
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.warning(
                        "No se pudo crear configuración contable para %s: %s",
                        company.name, e
                    )

    # 2) Crear ubicación "Préstamos Temporales" por almacén de tipo loans (si tus campos existen)
    StockWarehouse = registry.get('stock.warehouse')
    StockLocation  = registry.get('stock.location')
    if StockWarehouse and StockLocation:
        su_env = api.Environment(cr, SUPERUSER_ID, {})
        Warehouse = su_env['stock.warehouse']
        Location  = su_env['stock.location']

        for wh in Warehouse.search([('warehouse_type', '=', 'loans')]):
            # parent = ubicación de stock principal del almacén
            parent_loc = wh.lot_stock_id
            if not parent_loc:
                continue

            temp_loc = Location.search([
                ('name', '=', 'Préstamos Temporales'),
                ('location_id', '=', parent_loc.id),
            ], limit=1)

            if not temp_loc:
                try:
                    Location.create({
                        'name': 'Préstamos Temporales',
                        'location_id': parent_loc.id,
                        'usage': 'internal',
                    })
                except Exception as e:
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.warning("No se pudo crear ubicación temporal: %s", e)


def uninstall_hook(env):
    """Hook ejecutado antes de la desinstalación del módulo (Odoo 18: recibe env)."""
        #Odoo do this -_<
    pass
