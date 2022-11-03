# Copyright (C) 2018-2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest
import tensorflow as tf
from common.tf_layer_test_class import CommonTFLayerTest
from common.utils.tf_utils import mix_array_with_value


class TestIsFinite(CommonTFLayerTest):
    def _prepare_input(self, inputs_info):
        assert 'x' in inputs_info, "Test error: inputs_info must contain `x`"
        x_shape = inputs_info['x']
        inputs_data = {}
        data = np.random.randint(-50, 50, x_shape).astype(np.float32)
        # mix data with np.inf and np.nan
        data = mix_array_with_value(data, np.nan)
        inputs_data['x'] = mix_array_with_value(data, np.inf)
        return inputs_data

    def create_is_finite_net(self, x_shape, x_type):
        tf.compat.v1.reset_default_graph()
        # Create the graph and model
        with tf.compat.v1.Session() as sess:
            x = tf.compat.v1.placeholder(x_type, x_shape, 'x')
            tf.raw_ops.IsFinite(x=x, name='is_finite')
            tf.compat.v1.global_variables_initializer()
            tf_net = sess.graph_def

        return tf_net, None

    test_data_basic = [
        dict(x_shape=[2], x_type=tf.float32),
        dict(x_shape=[3, 4], x_type=tf.float32),
        dict(x_shape=[5, 2, 4], x_type=tf.float32),
    ]

    @pytest.mark.parametrize("params", test_data_basic)
    @pytest.mark.xfail(reason="94741")
    @pytest.mark.precommit_tf_fe
    def test_is_finite_basic(self, params, ie_device, precision, ir_version, temp_dir,
                             use_new_frontend, use_old_api):
        if not use_new_frontend:
            pytest.skip("IsFinite operation is not supported via legacy frontend.")
        self._test(*self.create_is_finite_net(**params),
                   ie_device, precision, ir_version, temp_dir=temp_dir,
                   use_new_frontend=use_new_frontend, use_old_api=use_old_api)