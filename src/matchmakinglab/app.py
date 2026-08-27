import click

from matchmakinglab.core.state import PlatformState
from matchmakinglab.matchmakers import BradleyTerryFactory


@click.command()
def cli():

    # Initialisation
    factory = BradleyTerryFactory()

    platform = factory.create_platform()
    generator = factory.create_generator()

    state = PlatformState()
