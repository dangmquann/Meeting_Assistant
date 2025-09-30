#TODO: Create arXiv clientfrom src.config import get_settings

from .client import ArxivClient
from controller.config import get_settings


def make_arxiv_client() -> ArxivClient:
    """Factory function to create an arXiv client instance.

    :returns: An instance of the arXiv client
    :rtype: ArxivClient
    """
    # Get settings from centralized config
    settings = get_settings()

    # Create arXiv client with explicit settings
    client = ArxivClient(settings=settings.arxiv)

    return client