
import json
import os
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2 = boto3.client("ec2")

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

REQUIRED_TAGS = {
    "AutoSchedule": "enabled",
    "Environment": "dev",
}


def lambda_handler(event, context):
    action = event.get(
        "action",
        os.environ.get("ACTION", "stop")
    ).lower()

    if action not in ("stop", "start"):
        raise ValueError("action must be 'stop' or 'start'.")

    target_state = "running" if action == "stop" else "stopped"

    response = ec2.describe_instances(
        Filters=[
            {"Name": "tag:AutoSchedule", "Values": ["enabled"]},
            {"Name": "tag:Environment", "Values": ["dev"]},
            {"Name": "instance-state-name", "Values": [target_state]},
        ]
    )

    results = []

    for reservation in response.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            instance_id = instance["InstanceId"]
            tags = {
                tag["Key"]: tag["Value"]
                for tag in instance.get("Tags", [])
            }

            if any(tags.get(k) != v for k, v in REQUIRED_TAGS.items()):
                logger.warning("Skipping %s: required tags missing", instance_id)
                continue

            if DRY_RUN:
                logger.info("DRY RUN: would %s instance %s", action, instance_id)
                results.append({
                    "instance_id": instance_id,
                    "action": action,
                    "dry_run": True,
                    "result": "would perform action",
                })
                continue

            try:
                if action == "stop":
                    ec2.stop_instances(InstanceIds=[instance_id])
                else:
                    ec2.start_instances(InstanceIds=[instance_id])

                logger.info("%s request submitted for %s", action, instance_id)
                results.append({
                    "instance_id": instance_id,
                    "action": action,
                    "dry_run": False,
                    "result": "request submitted",
                })

            except ClientError:
                logger.exception("Failed to %s %s", action, instance_id)
                results.append({
                    "instance_id": instance_id,
                    "action": action,
                    "dry_run": False,
                    "result": "error",
                })

    return {
        "statusCode": 200,
        "body": json.dumps({
            "action": action,
            "dry_run": DRY_RUN,
            "processed_count": len(results),
            "results": results,
        }),
    }