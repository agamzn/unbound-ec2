#!/usr/bin/env python
# coding: utf-8

__license__ = """
Copyright (c) 2013 Will Maier <wcmaier@m.aier.us>

Permission to use, copy, modify, and distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

import os
import random
import boto3

class Meta(object):
    ec2 = boto3.resource('ec2')
    #TODO: Config files? 
    zone = os.environ.get("ZONE", ".example.com.").encode("ascii")
    ttl = int(os.environ.get("TTL", "300"))


def init(id, cfg):
    if not Meta.zone.endswith("."):
        zone += "."

    log_info("unbound_ec2: Connected to AWS")
    log_info("unbound_ec2: authoritative for zone %s" % M.zone)

    return True

def deinit(id):
    return True

def inform_super(id, qstate, superqstate, qdata):
    return True

def operate(id, event, qstate, qdata):

    if (event == MODULE_EVENT_NEW) or (event == MODULE_EVENT_PASS):
        if (qstate.qinfo.qtype == RR_TYPE_A) or (qstate.qinfo.qtype == RR_TYPE_ANY):
            qname = qstate.qinfo.qname_str
            if qname.endswith(M.zone):
                log_info("unbound_ec2: handling forward query for %s" % qname)
                return handle_forward(id, event, qstate, qdata)

        # Fall through; pass on this request.
        return handle_pass(id, event, qstate, qdata)

    if event == MODULE_EVENT_MODDONE:
        return handle_finished(id, event, qstate, qdata)

    return handle_error(id, event, qstate, qdata)


def determine_address(instance):
    return (instance.tags.get('Address')
            or instance.ip_address
            or instance.private_ip_address).encode("ascii")


def handle_forward(id, event, qstate, qdata):

    qname = qstate.qinfo.qname_str
    msg = DNSMessage(qname, RR_TYPE_A, RR_CLASS_IN, PKT_QR | PKT_RA | PKT_AA)

    #TODO: move this to Meta.
    #TODO: Account for multiple tag searches. 
    # Ex: ansible-configserver.openshift.qs.use1
    # - might need auth for multiple zones? 
    reservations = ec2.get_all_instances(filters={
        "instance-state-name": "running",
        "tag:Name": qname.strip("."),
    })
    instances = [instance for reservation in reservations
                 for instance in reservation.instances]

    if len(instances) == 0:
        qstate.return_rcode = RCODE_NXDOMAIN
    else:
        qstate.return_rcode = RCODE_NOERROR
        random.shuffle(instances)
        for instance in instances:
            address = determine_address(instance)
            record = "%s %d IN A %s" % (qname, Meta.ttl, address)
            msg.answer.append(record)

    if not msg.set_return_msg(qstate):
        qstate.ext_state[id] = MODULE_ERROR
        return True

    qstate.return_msg.rep.security = 2
    qstate.ext_state[id] = MODULE_FINISHED
    return True

def handle_pass(id, event, qstate, qdata):
    qstate.ext_state[id] = MODULE_WAIT_MODULE
    return True

def handle_finished(id, event, qstate, qdata):
    qstate.ext_state[id] = MODULE_FINISHED
    return True

def handle_error(id, event, qstate, qdata):
    log_err("unbound_ec2: bad event")
    qstate.ext_state[id] = MODULE_ERROR
    return True
