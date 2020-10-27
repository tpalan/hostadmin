{
    'name': "hostadmin",

    'summary': """
	Manaing customer's domains and generate invoices
    """,

    'description': """
	Administration of customer domain hostings
    """,

    'author': "palan3 IT solutions OG",
    'website': "http://www.palan.at",

    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account'],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
        'data/data.xml'
    ],
    # only loaded in demonstration mode
    'demo': [
    ],
}
