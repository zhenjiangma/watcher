# -*- encoding: utf-8 -*-
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
from oslo_log import log

from watcher._i18n import _
from watcher.decision_engine.strategy.strategies import base

LOG = log.getLogger(__name__)


class DummyWithResize(base.DummyBaseStrategy):
    """Dummy strategy used for integration testing via Tempest

    *Description*

    This strategy does not provide any useful optimization. Its only purpose
    is to be used by Tempest tests.

    *Requirements*

    <None>

    *Limitations*

    Do not use in production.

    *Spec URL*

    <None>
    """

    NOP = "nop"
    SLEEP = "sleep"

    def pre_execute(self):
        self._pre_execute()

    def do_execute(self):
        para1 = self.input_parameters.para1
        para2 = self.input_parameters.para2
        LOG.debug("Executing Dummy strategy with para1=%(p1)f, para2=%(p2)s",
                  {'p1': para1, 'p2': para2})
        parameters = {'message': 'hello World'}
        self.solution.add_action(action_type=self.NOP,
                                 input_parameters=parameters)

        parameters = {'message': 'Welcome'}
        self.solution.add_action(action_type=self.NOP,
                                 input_parameters=parameters)

        self.solution.add_action(action_type=self.SLEEP,
                                 input_parameters={'duration': 5.0})
        self.solution.add_action(
            action_type='migrate',
            resource_id='b199db0c-1408-4d52-b5a5-5ca14de0ff36',
            input_parameters={
                'source_node': 'compute2',
                'destination_node': 'compute3',
                'migration_type': 'live'})

        self.solution.add_action(
            action_type='migrate',
            resource_id='8db1b3c1-7938-4c34-8c03-6de14b874f8f',
            input_parameters={
                'source_node': 'compute2',
                'destination_node': 'compute3',
                'migration_type': 'live'}
        )
        self.solution.add_action(
            action_type='resize',
            resource_id='8db1b3c1-7938-4c34-8c03-6de14b874f8f',
            input_parameters={'flavor': 'x2'}
        )

    def post_execute(self):
        pass

    @classmethod
    def get_name(cls):
        return "dummy_with_resize"

    @classmethod
    def get_display_name(cls):
        return _("Dummy strategy with resize")

    @classmethod
    def get_translatable_display_name(cls):
        return "Dummy strategy with resize"

    @classmethod
    def get_schema(cls):
        # Mandatory default setting for each element
        return {
            "properties": {
                "para1": {
                    "description": "number parameter example",
                    "type": "number",
                    "default": 3.2,
                    "minimum": 1.0,
                    "maximum": 10.2,
                },
                "para2": {
                    "description": "string parameter example",
                    "type": "string",
                    "default": "hello"
                },
            },
        }
