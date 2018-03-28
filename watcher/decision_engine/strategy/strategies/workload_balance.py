# -*- encoding: utf-8 -*-
# Copyright (c) 2016 Intel Corp
#
# Authors: Junjie-Huang <junjie.huang@intel.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import division

from oslo_config import cfg
from oslo_log import log

from watcher._i18n import _
from watcher.common import exception as wexc
from watcher.decision_engine.model import element
from watcher.decision_engine.strategy.strategies import base

LOG = log.getLogger(__name__)


class WorkloadBalance(base.WorkloadStabilizationBaseStrategy):
    """[PoC]Workload balance using live migration

    *Description*

        It is a migration strategy based on the VM workload of physical
        servers. It generates solutions to move a workload whenever a server's
        CPU or RAM utilization % is higher than the specified threshold.
        The VM to be moved should make the host close to average workload
        of all compute nodes.

    *Requirements*

        * Hardware: compute node should use the same physical CPUs/RAMs
        * Software: Ceilometer component ceilometer-agent-compute running
          in each compute node, and Ceilometer API can report such telemetry
          "cpu_util" and "memory.resident" successfully.
        * You must have at least 2 physical compute nodes to run this strategy.

    *Limitations*

       - This is a proof of concept that is not meant to be used in production
       - We cannot forecast how many servers should be migrated. This is the
         reason why we only plan a single virtual machine migration at a time.
         So it's better to use this algorithm with `CONTINUOUS` audits.
       - It assume that live migrations are possible
    """

    # The meter to report CPU utilization % of VM in ceilometer
    # Unit: %, value range is [0 , 100]
    CPU_METER_NAME = "cpu_util"

    # The meter to report memory resident of VM in ceilometer
    # Unit: MB
    MEM_METER_NAME = "memory.resident"

    DATASOURCE_METRICS = ['instance_cpu_usage', 'instance_ram_usage']

    MIGRATION = "migrate"

    def __init__(self, config, osc=None):
        """Workload balance using live migration

        :param config: A mapping containing the configuration of this strategy
        :type config: :py:class:`~.Struct` instance
        :param osc: :py:class:`~.OpenStackClients` instance
        """
        super(WorkloadBalance, self).__init__(config, osc)
        # the migration plan will be triggered when the CPU or RAM
        # utilization % reaches threshold
        self._meter = None

    @classmethod
    def get_name(cls):
        return "workload_balance"

    @classmethod
    def get_display_name(cls):
        return _("Workload Balance Migration Strategy")

    @classmethod
    def get_translatable_display_name(cls):
        return "Workload Balance Migration Strategy"

    @property
    def granularity(self):
        return self.input_parameters.get('granularity', 300)

    @classmethod
    def get_schema(cls):
        # Mandatory default setting for each element
        return {
            "properties": {
                "metrics": {
                    "description": "Workload balance based on metrics: "
                                   "cpu or ram utilization",
                    "type": "string",
                    "choice": ["cpu_util", "memory.resident"],
                    "default": "cpu_util"
                },
                "threshold": {
                    "description": "workload threshold for migration",
                    "type": "number",
                    "default": 25.0
                },
                "period": {
                    "description": "aggregate time period of ceilometer",
                    "type": "number",
                    "default": 300
                },
                "granularity": {
                    "description": "The time between two measures in an "
                                   "aggregated timeseries of a metric.",
                    "type": "number",
                    "default": 300
                },
            },
        }

    @classmethod
    def get_config_opts(cls):
        return [
            cfg.ListOpt(
                "datasources",
                help="Datasources to use in order to query the needed metrics."
                     " If one of strategy metric isn't available in the first"
                     " datasource, the next datasource will be chosen.",
                item_type=cfg.types.String(choices=['gnocchi', 'ceilometer',
                                                    'monasca']),
                default=['gnocchi', 'ceilometer', 'monasca'])
        ]

    def get_available_compute_nodes(self):
        default_node_scope = [element.ServiceState.ENABLED.value]
        return {uuid: cn for uuid, cn in
                self.compute_model.get_all_compute_nodes().items()
                if cn.state == element.ServiceState.ONLINE.value and
                cn.status in default_node_scope}

    def calculate_used_resource(self, node):
        """Calculate the used vcpus, memory and disk based on VM flavors"""
        instances = self.compute_model.get_node_instances(node)
        vcpus_used = 0
        memory_mb_used = 0
        disk_gb_used = 0
        for instance in instances:
            vcpus_used += instance.vcpus
            memory_mb_used += instance.memory
            disk_gb_used += instance.disk

        return vcpus_used, memory_mb_used, disk_gb_used

    def choose_instance_to_migrate(self, hosts, avg_workload, workload_cache):
        """Pick up an active instance instance to migrate from provided hosts

        :param hosts: the array of dict which contains node object
        :param avg_workload: the average workload value of all nodes
        :param workload_cache: the map contains instance to workload mapping
        """
        for instance_data in hosts:
            source_node = instance_data['node']
            source_instances = self.compute_model.get_node_instances(
                source_node)
            if source_instances:
                delta_workload = instance_data['workload'] - avg_workload
                min_delta = 1000000
                instance_id = None
                for instance in source_instances:
                    try:
                        # select the first active VM to migrate
                        if (instance.state !=
                                element.InstanceState.ACTIVE.value):
                            LOG.debug("Instance not active, skipped: %s",
                                      instance.uuid)
                            continue
                        current_delta = (
                            delta_workload - workload_cache[instance.uuid])
                        if 0 <= current_delta < min_delta:
                            min_delta = current_delta
                            instance_id = instance.uuid
                    except wexc.InstanceNotFound:
                        LOG.error("Instance not found; error: %s",
                                  instance_id)
                if instance_id:
                    return (source_node,
                            self.compute_model.get_instance_by_uuid(
                                instance_id))
            else:
                LOG.info("VM not found from node: %s",
                         source_node.uuid)

    def filter_destination_hosts(self, hosts, instance_to_migrate,
                                 avg_workload, workload_cache):
        """Only return hosts with sufficient available resources"""
        required_cores = instance_to_migrate.vcpus
        required_disk = instance_to_migrate.disk
        required_mem = instance_to_migrate.memory

        # filter nodes without enough resource
        destination_hosts = []
        src_instance_workload = workload_cache[instance_to_migrate.uuid]
        for instance_data in hosts:
            host = instance_data['node']
            workload = instance_data['workload']
            # calculate the available resources
            cores_used, mem_used, disk_used = self.calculate_used_resource(
                host)
            cores_available = host.vcpus - cores_used
            disk_available = host.disk - disk_used
            mem_available = host.memory - mem_used
            if (cores_available >= required_cores and
                    mem_available >= required_mem and
                    disk_available >= required_disk):
                if (self._meter == self.CPU_METER_NAME and
                    ((src_instance_workload + workload) <
                     self.threshold / 100 * host.vcpus)):
                    destination_hosts.append(instance_data)
                if (self._meter == self.MEM_METER_NAME and
                    ((src_instance_workload + workload) <
                     self.threshold / 100 * host.memory)):
                    destination_hosts.append(instance_data)

        return destination_hosts

    def group_hosts_by_cpu_or_ram_util(self):
        """Calculate the workloads of each node

        try to find out the nodes which have reached threshold
        and the nodes which are under threshold.
        and also calculate the average workload value of all nodes.
        and also generate the instance workload map.
        """

        nodes = self.get_available_compute_nodes()
        cluster_size = len(nodes)
        if not nodes:
            raise wexc.ClusterEmpty()
        overload_hosts = []
        nonoverload_hosts = []
        # total workload of cluster
        cluster_workload = 0.0
        # use workload_cache to store the workload of VMs for reuse purpose
        workload_cache = {}
        for node_id in nodes:
            node = self.compute_model.get_node_by_uuid(node_id)
            instances = self.compute_model.get_node_instances(node)
            node_workload = 0.0
            for instance in instances:
                util = None
                try:
                    util = self.datasource_backend.statistic_aggregation(
                        instance.uuid, self._meter, self._period,
                        self._granularity, aggregation='mean',
                        dimensions=dict(resource_id=instance.uuid))
                except Exception as exc:
                    LOG.exception(exc)
                    LOG.error("Can not get %s from %s", self._meter,
                              self.config.datasource)
                    continue
                if util is None:
                    LOG.debug("Instance (%s): %s is None",
                              instance.uuid, self._meter)
                    continue
                if self._meter == self.CPU_METER_NAME:
                    workload_cache[instance.uuid] = (util *
                                                     instance.vcpus / 100)
                else:
                    workload_cache[instance.uuid] = util
                node_workload += workload_cache[instance.uuid]
                LOG.debug("VM (%s): %s %f", instance.uuid, self._meter,
                          util)

            cluster_workload += node_workload
            if self._meter == self.CPU_METER_NAME:
                node_util = node_workload / node.vcpus * 100
            else:
                node_util = node_workload / node.memory * 100

            instance_data = {
                'node': node, self._meter: node_util,
                'workload': node_workload}
            if node_util >= self.threshold:
                # mark the node to release resources
                overload_hosts.append(instance_data)
            else:
                nonoverload_hosts.append(instance_data)

        avg_workload = cluster_workload / cluster_size

        return overload_hosts, nonoverload_hosts, avg_workload, workload_cache

    def pre_execute(self):
        """Pre-execution phase

        This can be used to fetch some pre-requisites or data.
        """
        LOG.info("Initializing Workload Balance Strategy")

        if not self.compute_model:
            raise wexc.ClusterStateNotDefined()

        if self.compute_model.stale:
            raise wexc.ClusterStateStale()

        LOG.debug(self.compute_model.to_string())

    def do_execute(self):
        """Strategy execution phase

        This phase is where you should put the main logic of your strategy.
        """
        self.threshold = self.input_parameters.threshold
        self._period = self.input_parameters.period
        self._meter = self.input_parameters.metrics
        self._granularity = self.input_parameters.granularity
        source_nodes, target_nodes, avg_workload, workload_cache = (
            self.group_hosts_by_cpu_or_ram_util())

        if not source_nodes:
            LOG.debug("No hosts require optimization")
            return self.solution

        if not target_nodes:
            LOG.warning("No hosts current have CPU utilization under %s "
                        "percent, therefore there are no possible target "
                        "hosts for any migration",
                        self.threshold)
            return self.solution

        # choose the server with largest cpu_util
        source_nodes = sorted(source_nodes,
                              reverse=True,
                              key=lambda x: (x[self._meter]))

        instance_to_migrate = self.choose_instance_to_migrate(
            source_nodes, avg_workload, workload_cache)
        if not instance_to_migrate:
            return self.solution
        source_node, instance_src = instance_to_migrate
        # find the hosts that have enough resource for the VM to be migrated
        destination_hosts = self.filter_destination_hosts(
            target_nodes, instance_src, avg_workload, workload_cache)
        # sort the filtered result by workload
        # pick up the lowest one as dest server
        if not destination_hosts:
            # for instance.
            LOG.warning("No proper target host could be found, it might "
                        "be because of there's no enough CPU/Memory/DISK")
            return self.solution
        destination_hosts = sorted(destination_hosts,
                                   key=lambda x: (x[self._meter]))
        # always use the host with lowerest CPU utilization
        mig_destination_node = destination_hosts[0]['node']
        # generate solution to migrate the instance to the dest server,
        if self.compute_model.migrate_instance(
                instance_src, source_node, mig_destination_node):
            parameters = {'migration_type': 'live',
                          'source_node': source_node.uuid,
                          'destination_node': mig_destination_node.uuid}
            self.solution.add_action(action_type=self.MIGRATION,
                                     resource_id=instance_src.uuid,
                                     input_parameters=parameters)

    def post_execute(self):
        """Post-execution phase

        This can be used to compute the global efficacy
        """
        self.solution.model = self.compute_model

        LOG.debug(self.compute_model.to_string())
