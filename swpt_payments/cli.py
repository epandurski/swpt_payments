import click
from os import environ
from datetime import datetime, timezone, timedelta
from flask.cli import with_appcontext
from . import procedures


@click.group('swpt_payments')
def swpt_payments():
    """Perform swpt_payments specific operations."""


@swpt_payments.command()
@with_appcontext
@click.argument('queue_name')
def subscribe(queue_name):  # pragma: no cover
    """Subscribe a queue for the observed events and messages.

    QUEUE_NAME specifies the name of the queue.

    """

    from .extensions import broker, MAIN_EXCHANGE_NAME
    from . import actors  # noqa

    channel = broker.channel
    channel.exchange_declare(MAIN_EXCHANGE_NAME)
    click.echo(f'Declared "{MAIN_EXCHANGE_NAME}" direct exchange.')

    if environ.get('APP_USE_LOAD_BALANCING_EXCHANGE', '') not in ['', 'False']:
        bind = channel.exchange_bind
        unbind = channel.exchange_unbind
    else:
        bind = channel.queue_bind
        unbind = channel.queue_unbind
    bind(queue_name, MAIN_EXCHANGE_NAME, queue_name)
    click.echo(f'Subscribed "{queue_name}" to "{MAIN_EXCHANGE_NAME}.{queue_name}".')

    for actor in [broker.get_actor(actor_name) for actor_name in broker.get_declared_actors()]:
        if 'event_subscription' in actor.options:
            routing_key = f'events.{actor.actor_name}'
            if actor.options['event_subscription']:
                bind(queue_name, MAIN_EXCHANGE_NAME, routing_key)
                click.echo(f'Subscribed "{queue_name}" to "{MAIN_EXCHANGE_NAME}.{routing_key}".')
            else:
                unbind(queue_name, MAIN_EXCHANGE_NAME, routing_key)
                click.echo(f'Unsubscribed "{queue_name}" from "{MAIN_EXCHANGE_NAME}.{routing_key}".')


@swpt_payments.command('flush_payment_orders')
@with_appcontext
@click.option('-d', '--days', type=float, help='The number of days.')
def flush_payment_orders(days):
    """Delete finalized payment orders older than a given number of days.

    If the number of days is not specified, the value of the
    environment variable APP_FLUSH_PAYMENT_ORDERS_DAYS is taken. If it
    is not set, the default number of days is 30.

    """

    # TODO: The current method of flushing may consume considerable
    # amount of database resources for quite some time. This could
    # potentially be a problem.

    days = days or int(environ.get('APP_FLUSH_PAYMENT_ORDERS_DAYS', '30'))
    cutoff_ts = datetime.now(tz=timezone.utc) - timedelta(days=days)
    n = procedures.flush_payment_orders(cutoff_ts)
    if n == 1:
        click.echo(f'1 payment order has been deleted.')
    elif n > 1:
        click.echo(f'{n} payment orders have been deleted.')


@swpt_payments.command('flush_payment_proofs')
@with_appcontext
@click.option('-d', '--days', type=float, help='The number of days.')
def flush_payment_proofs(days):
    """Delete payment proofs older than a given number of days.

    If the number of days is not specified, the value of the
    environment variable APP_FLUSH_PAYMENT_PROOFS_DAYS is taken. If it
    is not set, the default number of days is 180.

    """

    # TODO: The current method of flushing may consume considerable
    # amount of database resources for quite some time. This could
    # potentially be a problem.

    days = days or int(environ.get('APP_FLUSH_PAYMENT_PROOFS_DAYS', '180'))
    cutoff_ts = datetime.now(tz=timezone.utc) - timedelta(days=days)
    n = procedures.flush_payment_proofs(cutoff_ts)
    if n == 1:
        click.echo(f'1 payment proof has been deleted.')
    elif n > 1:
        click.echo(f'{n} payment proofs have been deleted.')
