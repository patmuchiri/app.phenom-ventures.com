from routeros_api import RouterOsApiPool
from django.conf import settings

def configure_mikrotik_queue(client, activate=True):
    try:
        # Connect to MikroTik router
        connection = RouterOsApiPool(
            settings.MIKROTIK_HOST,
            username=settings.MIKROTIK_USERNAME,
            password=settings.MIKROTIK_PASSWORD,
            port=settings.MIKROTIK_PORT,
            plaintext_login=True
        )
        
        api = connection.get_api()
        
        # Remove existing queue if it exists
        queue_list = api.get_resource('/queue/simple').get(name=f"Client-{client.name}")
        for queue in queue_list:
            api.get_resource('/queue/simple').remove(id=queue['id'])
        
        if activate:
            # Create new queue for client
            api.get_resource('/queue/simple').add(
                name=f"Client-{client.name}",
                target=client.ip_address,
                max_limit=f"{client.upload_limit}/{client.download_limit}",
                disabled="no"
            )
        
        connection.disconnect()
        return True
    except Exception as e:
        print(f"Error configuring MikroTik: {str(e)}")
        return False