# -*- encoding: utf-8 -*-
#
# Copyright © 2016 Servionica
##
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import abc


class ServiceManagerBase(object):

    @abc.abstractproperty
    def service_name(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def api_version(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def publisher_id(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def conductor_topic(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def status_topic(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def notification_topics(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def conductor_endpoints(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def status_endpoints(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def notification_endpoints(self):
        raise NotImplementedError()
