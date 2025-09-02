{
    'name': 'Sistema Avanzado de Préstamos de Productos',
    'version': '18.0.2.0.0',
    'summary': 'Sistema completo de gestión de préstamos con integración contable',
    'description': """
Sistema Avanzado de Préstamos de Productos
==========================================

Un módulo completo para gestionar préstamos de productos con funcionalidades empresariales avanzadas.

Características Principales:
============================
* **Tipos de almacén especializados** para préstamos
* **Gestión granular de préstamos** por producto y número de serie
* **Períodos de prueba** con conversión automática a ventas
* **Wizard de resolución** para manejar compras/devoluciones/préstamos continuos
* **Seguimiento detallado** con estados específicos y trazabilidad completa
* **Integración contable completa** con asientos de compromiso y riesgo
* **Sistema de alertas** automático para préstamos vencidos
* **Dashboard analítico** con métricas en tiempo real
* **Validaciones avanzadas** de stock considerando reservas y concurrencia
* **Límites configurables** por cliente (cantidad y valor)
* **Notificaciones automáticas** por email y actividades

Funcionalidades Técnicas:
=========================
* **Arquitectura modular** con separación clara de responsabilidades
* **Cálculos de stock optimizados** que distinguen entre stock general y prestado
* **Manejo de rastreo** tanto por cantidad como por números de serie/lote
* **Validaciones de concurrencia** para entornos multi-usuario
* **Sistema de valoración** que mantiene costos originales en conversiones
* **Ubicaciones dinámicas** según frecuencia del cliente
* **Wizards intuitivos** para procesos complejos
* **Reportes SQL optimizados** con índices para gran volumen de datos

Casos de Uso:
=============
* Préstamos de equipos o herramientas a empleados
* Productos en consignación con clientes
* Períodos de prueba antes de compra
* Préstamos de muestras o prototipos
* Gestión de activos temporales

Integraciones:
==============
* **Módulo de Inventario**: Gestión completa de ubicaciones y movimientos
* **Módulo de Ventas**: Conversión automática de préstamos a órdenes de venta
* **Módulo de Contabilidad**: Asientos automáticos de compromiso y valoración
* **Sistema de Actividades**: Alertas y seguimiento automatizado

    """,
    'author': 'Javier - AteneoLab',
    'website': 'https://www.ateneolab.com',
    'category': 'Inventory/Inventory',
    'depends': [
        'base',
        'stock', 
        'sale',
        'account',
        'mail',
    ],
    'data': [
        # ==========================================
        # SECURITY - DEBE CARGARSE PRIMERO
        # ==========================================
        'security/product_loans_security.xml',
        'security/ir.model.access.csv',
        
        # ==========================================
        # DATA - CONFIGURACIÓN INICIAL Y DEMOS
        # ==========================================
        'data/demo_data.xml',
        'data/loan_accounting_data.xml',
        'data/ir_cron_data.xml',
        
        # ==========================================
        # WIZARD VIEWS - ANTES QUE LAS VISTAS QUE LAS REFERENCIAN
        # ==========================================
        'wizard/loan_return_wizard_views.xml',
        'wizard/loan_resolution_wizard_views.xml',
        
        # ==========================================
        # MODEL VIEWS - ORDEN ESPECÍFICO POR DEPENDENCIAS
        # ==========================================
        'views/stock_warehouse_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_picking_type_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/loan_tracking_detail_views.xml',
        'views/loan_accounting_views.xml',
        'views/loan_report_views.xml',     
        # ==========================================
        # MENUS - AL FINAL (REFERENCIAN ACCIONES DE VISTAS ANTERIORES)
        # ==========================================
        'views/product_loans_menus_complete.xml',
        # ==========================================
        # ANALYTICS - CONVERSION DASHBOARD  
        # ==========================================
        'views/loan_analytics_board.xml', 
        # ==========================================
        # DEBUG Y DESARROLLO
        # ==========================================
        'views/debug_views.xml',
    ],
    'demo': [
        'demo/loan_demo_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': [],
    },
    'post_init_hook': 'post_install_hook',
    'uninstall_hook': 'uninstall_hook',
}