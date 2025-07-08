from routeros_api import RouterOsApiPool
from routeros_api.exceptions import RouterOsApiConnectionError
from .models import MikrotikRouter
import logging

logger = logging.getLogger(__name__)

class MikrotikManager:
    def __init__(self, router_id):
        router = MikrotikRouter.objects.get(id=router_id)
        self.connection = RouterOsApi(
            host=router.ip_address,
            username=router.username,
            password=router.password,
            port=router.api_port,
            use_ssl=False,
            plaintext_login=True
        )
    
    def update_client_bandwidth(self, client_ip, download_speed, upload_speed):
        try:
            api = self.connection
            queue_list = api.get_resource('/queue/simple')
            
            # Check if queue exists
            queues = queue_list.get(address=client_ip)
            
            if queues:
                # Update existing queue
                queue = queues[0]
                queue_list.set(
                    id=queue['id'],
                    max_limit=f"{download_speed}/1M",
                    burst_limit=f"{download_speed}/1M",
                    burst_threshold=f"{download_speed}/1M",
                    burst_time="00:00:30",
                    limit_at=f"{download_speed}/1M",
                    priority=8,
                    queue="default/default",
                    name=f"Client-{client_ip}",
                    target=client_ip,
                    dst="0.0.0.0/0",
                    disabled="no"
                )
            else:
                # Create new queue
                queue_list.add(
                    name=f"Client-{client_ip}",
                    target=client_ip,
                    dst="0.0.0.0/0",
                    max_limit=f"{download_speed}/1M",
                    burst_limit=f"{download_speed}/1M",
                    burst_threshold=f"{download_speed}/1M",
                    burst_time="00:00:30",
                    limit_at=f"{download_speed}/1M",
                    priority=8,
                    queue="default/default",
                    disabled="no"
                )
            return True
        except RouterOsApiConnectionError as e:
            logger.error(f"Mikrotik connection error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating bandwidth: {e}")
            return False
    
    def deactivate_client(self, client_ip):
        return self.update_client_bandwidth(client_ip, "1k", "1k")
    
    def close_connection(self):
        self.connection.disconnect()
