"""
.. module: lemur.plugins.lemur_vault.plugin
    :platform: Unix
    :copyright: (c) 2019
    :license: Apache, see LICENCE for more details.

    Plugin for uploading certificates and private key as secret to hashi vault
     that can be pulled down by end point nodes.

.. moduleauthor:: Christopher Jolley <chris@alwaysjolley.com>
"""
import hvac

#import lemur_vault
from flask import current_app

from lemur.common.defaults import common_name
from lemur.common.utils import parse_certificate
from lemur.plugins.bases import DestinationPlugin

from cryptography import x509
from cryptography.hazmat.backends import default_backend


class VaultDestinationPlugin(DestinationPlugin):
    """Hashicorp Vault Destination plugin for Lemur"""
    title = 'Vault'
    slug = 'hashi-vault-destination'
    description = 'Allow the uploading of certificates to Hashi Vault as secret'

    author = 'Christopher Jolley'
    author_url = 'https://github.com/alwaysjolley/lemur'

    options = [
        {
            'name': 'vaultMount',
            'type': 'str',
            'required': True,
            'validation': '^[a-zA-Z0-9]+$',
            'helpMessage': 'Must be a valid Vault secrets mount name!'
        },
        {
            'name': 'vaultPath',
            'type': 'str',
            'required': True,
            'validation': '^([a-zA-Z0-9_-]+/?)+$',
            'helpMessage': 'Must be a valid Vault secrets path'
        },
        {
            'name': 'objectName',
            'type': 'str',
            'required': False,
            'validation': '[0-9a-zA-Z:_-]+',
            'helpMessage': 'Name to bundle certs under, if blank use cn'
        },
        {
            'name': 'bundleChain',
            'type': 'select',
            'value': 'cert only',
            'available': [
                'Nginx',
                'Apache',
                'no chain'
            ],
            'required': True,
            'helpMessage': 'Bundle the chain into the certificate'
        }
    ]

    def __init__(self, *args, **kwargs):
        super(VaultDestinationPlugin, self).__init__(*args, **kwargs)

    def upload(self, name, body, private_key, cert_chain, options, **kwargs):
        """
        Upload certificate and private key

        :param private_key:
        :param cert_chain:
        :return:
        """
        cname = common_name(parse_certificate(body))
        secret = {'data':{}}
        key_name = '{0}.key'.format(cname)
        cert_name = '{0}.crt'.format(cname)
        chain_name = '{0}.chain'.format(cname)
        sans_name = '{0}.san'.format(cname)

        token = current_app.config.get('VAULT_TOKEN')
        url = current_app.config.get('VAULT_URL')

        mount = self.get_option('vaultMount', options)
        path = self.get_option('vaultPath', options)
        bundle = self.get_option('bundleChain', options)
        obj_name = self.get_option('objectName', options)

        client = hvac.Client(url=url, token=token)
        if obj_name:
            path = '{0}/{1}'.format(path, obj_name)
        else:
            path = '{0}/{1}'.format(path, cname)

        secret = get_secret(url, token, mount, path)
        

        if bundle == 'Nginx' and cert_chain:
            secret['data'][cert_name] = '{0}\n{1}'.format(body, cert_chain)
        elif bundle == 'Apache' and cert_chain:
            secret['data'][cert_name] = body
            secret['data'][chain_name] = cert_chain
        else:
            secret['data'][cert_name] = body
        secret['data'][key_name] = private_key
        san_list = get_san_list(body)
        if isinstance(san_list, list):
            secret['data'][sans_name] = san_list
        try:
            client.secrets.kv.v1.create_or_update_secret(
                path=path, mount_point=mount, secret=secret['data'])
        except ConnectionError as err:
            current_app.logger.exception(
                "Exception uploading secret to vault: {0}".format(err), exc_info=True)

def get_san_list(body):
    """ parse certificate for SAN names and return list, return empty list on error """
    try:
        byte_body = body.encode('utf-8')
        cert = x509.load_pem_x509_certificate(byte_body, default_backend())
        ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        return ext.value.get_values_for_type(x509.DNSName)
    except:
        pass
    return []

def get_secret(url, token, mount, path):
    result = {'data': {}}
    try:
        client = hvac.Client(url=url, token=token)
        result = client.secrets.kv.v1.read_secret(path=path, mount_point=mount)
    except:
        pass
    return result
