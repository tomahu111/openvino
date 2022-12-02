# Copyright (C) 2018-2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import unittest
from unittest.mock import Mock

import numpy as np
from generator import generator, generate

from openvino.frontend import (
    FrontEndManager,
    FrontEnd,
)  # pylint: disable=no-name-in-module,import-error
from openvino.runtime import Core
from openvino.tools.mo.convert_impl import prepare_ir


def base_args_config():
    args = argparse.Namespace()
    args.feManager = FrontEndManager()
    args.extensions = None
    # use new TF FE
    args.use_legacy_frontend = False
    args.use_new_frontend = True
    args.framework = "tf"
    args.model_name = None
    args.input_model = None
    args.input_model_is_text = False
    args.input_checkpoint = None
    args.saved_model_dir = None
    args.input_meta_graph = None
    args.saved_model_tags = None
    args.silent = True
    args.transform = []
    args.scale = None
    args.output = None
    args.input = None
    args.input_shape = None
    args.batch = None
    args.mean_values = None
    args.scale_values = None
    args.output_dir = os.getcwd()
    args.freeze_placeholder_with_value = None
    args.tensorflow_use_custom_operations_config = None
    args.transformations_config = None
    args.disable_fusing = None
    args.finegrain_fusing = None
    args.disable_resnet_optimization = None
    args.enable_concat_optimization = None
    args.static_shape = None
    args.disable_weights_compression = None
    args.reverse_input_channels = None
    args.data_type = None
    args.layout = None
    args.source_layout = None
    args.target_layout = None
    return args


try:
    import openvino_telemetry as tm
except ImportError:
    import openvino.tools.mo.utils.telemetry_stub as tm


@generator
class TestMoFreezePlaceholderTFFE(unittest.TestCase):
    def setUp(self):
        try:
            import tensorflow.compat.v1 as tf
        except ImportError:
            import tensorflow as tf

        tm.Telemetry.__init__ = Mock(return_value=None)
        tm.Telemetry.send_event = Mock()
        FrontEnd.add_extension = Mock()

        self.models = []
        tf.reset_default_graph()
        with tf.Session() as sess:
            x = tf.placeholder(tf.float32, [2, 2], 'in1')
            y = tf.placeholder(tf.float32, [2, 2], 'in2')
            tf.add(x, y, name="add")

            tf.global_variables_initializer()
            tf.io.write_graph(sess.graph, '.', 'model_fp32.pb', as_text=False)

        self.models.append("model_fp32.pb")

        tf.reset_default_graph()
        with tf.Session() as sess:
            x = tf.placeholder(tf.int32, [2, 3], 'in1')
            y = tf.placeholder(tf.int32, [2, 3], 'in2')
            tf.multiply(x, y, name="add")

            tf.global_variables_initializer()
            tf.io.write_graph(sess.graph, '.', 'model_int32.pb', as_text=False)

        self.models.append("model_int32.pb")

        tf.reset_default_graph()
        with tf.Session() as sess:
            x = tf.placeholder(tf.bool, [2, 3], 'in1')
            y = tf.placeholder(tf.bool, [2, 3], 'in2')
            tf.math.logical_and(x, y)

            tf.global_variables_initializer()
            tf.io.write_graph(sess.graph, '.', 'model_bool.pb', as_text=False)

        self.models.append("model_bool.pb")

        tf.reset_default_graph()
        with tf.Session() as sess:
            x = tf.placeholder(tf.float32, [3], 'in1')
            y = tf.placeholder(tf.float32, [3], 'in2')
            cond = tf.placeholder(tf.bool, [], 'cond')
            tf.where(cond, x, y)

            tf.global_variables_initializer()
            tf.io.write_graph(sess.graph, '.', 'model_bool2.pb', as_text=False)

        self.models.append("model_bool2.pb")

        tf.reset_default_graph()
        with tf.Session() as sess:
            x = tf.placeholder(tf.float32, [3], 'x')
            y = tf.placeholder(tf.float32, [3], 'y')
            z = tf.placeholder(tf.float32, [3], 'z')
            add = tf.add(x, y, name="add")
            tf.multiply(add, z, name="multiply")

            tf.global_variables_initializer()
            tf.io.write_graph(sess.graph, '.', 'model_three_inputs.pb', as_text=False)

        self.models.append("model_three_inputs.pb")

    def tearDown(self):
        for name in self.models:
            os.remove(name)

    def basic(self, input_model, argv_input, inputs, dtype, expected, freeze_placeholder_with_value=None,
              input_shape=None, only_conversion=False):
        args = base_args_config()
        args.input_model = input_model
        args.input = argv_input
        args.freeze_placeholder_with_value = freeze_placeholder_with_value
        args.input_shape = input_shape

        try:
            _, model = prepare_ir(args)
        except Exception as ex:
            self.fail("Model conversion failed due to error: {}".format(ex))

        if only_conversion:
            return

        ie = Core()
        exec_net = ie.compile_model(model, "CPU")
        req = exec_net.create_infer_request()
        results = req.infer(inputs)
        values = list(results.values())[0]
        if dtype is not None:
            assert values.dtype == dtype
        assert np.allclose(values, expected)

    @generate(
        *[
            (
                    "in1[1 4]->[1.0 2.0 3.0 4.0],in2[1 4]{f32}->[1.0 2.0 3.0 4.0]",
                    {},
                    np.array([2.0, 4.0, 6.0, 8.0]),
                    np.float32,
            ),
            (
                    "in2{f32}->[0.0 0.0 0.0 0.0]",
                    {"in1": np.array([[1.0, 2.0], [3.0, 4.0]])},
                    np.array([[1.0, 2.0], [3.0, 4.0]]),
                    np.float32,
            ),
            (
                    "in2->[1.0 15.0 15.5 1.0]",
                    {"in1": np.array([[2.0, 4.0], [12.0, 8.0]])},
                    np.array([[3.0, 19.0], [27.5, 9.0]]),
                    np.float32,
            ),
            (
                    "in1[1 4]{i32}->[1 2 3 4],in2[1 4]{i32}->[1 2 3 4]",
                    {},
                    np.array([2.0, 4.0, 6.0, 8.0]),
                    np.int32,
            ),
        ],
    )
    def test_fp32(self, input_freezing_value, inputs, expected,
                  dtype):
        self.basic("model_fp32.pb", input_freezing_value, inputs, dtype, expected)

    @generate(
        *[
            (
                    "in1[1 4]->[1 2 3 4],in2[1 4]{i32}->[1 2 3 4]",
                    {},
                    np.array([1, 4, 9, 16]),
                    np.int32,
            ),
            (
                    "in2->[2 5 6 7 3 2]",
                    {"in1": np.array([[2, 4, 1], [1, 2, 8]])},
                    np.array([[4, 20, 6], [7, 6, 16]]),
                    np.int32,
            ),
        ],
    )
    def test_int32(self, input_freezing_value, inputs, expected,
                   dtype=None):
        self.basic("model_int32.pb", input_freezing_value, inputs, dtype, expected)

    @generate(
        *[
            (
                    "in1[2]->[True False],in2[2]->[True True]",
                    {},
                    np.array([True, False], dtype=bool),
                    bool,
            ),
            (
                    "in2[2,3]->[True,True,False,True,True,False]",
                    {"in1": np.array([[False, True, True], [False, True, True]], dtype=bool)},
                    np.array([[False, True, False], [False, True, False]], dtype=bool),
                    bool,
            ),
            (
                    "in2[]->True",
                    {"in1": np.array([[False, True, True], [False, True, True]], dtype=bool)},
                    np.array([[False, True, True], [False, True, True]], dtype=bool),
                    bool,
            ),
        ],
    )
    def test_bool(self, input_freezing_value, inputs, expected,
                  dtype=None):
        self.basic("model_bool.pb", input_freezing_value, inputs, dtype, expected)

    @generate(
        *[
            (
                    "in1[3]->[1 2 3],in2[3]->[4 5 6],cond->False",
                    {},
                    np.array([4, 5, 6], dtype=np.float32),
                    np.float32,
                    None
            ),
            (
                    None,
                    {"in1": np.array([2.0, 4.0, 6.0], dtype=np.float32),
                     "in2": np.array([1.0, 3.0, 5.0], dtype=np.float32)},
                    np.array([2, 4, 6], dtype=np.float32),
                    np.float32,
                    "cond->False",
                    None,
                    True  # fill a bug to investigate why compilation of this model is hang on
            ),
            # case: input_shape + freeze_placeholder_with_value
            (
                    None,
                    {"in2": np.array([1.0, 3.0, 5.0], dtype=np.float32)},
                    np.array([2, 4, 6], dtype=np.float32),
                    np.float32,
                    "in1->[2.0 4.0 6.0],cond->True",
                    "[3]",
                    False
            ),
        ],
    )
    def test_bool2(self, input_freezing_value, inputs, expected,
                   dtype=None, freeze_placeholder_with_value=None, input_shape=None, only_conversion=False):
        self.basic("model_bool2.pb", input_freezing_value, inputs, dtype, expected, freeze_placeholder_with_value,
                   input_shape, only_conversion)

    @generate(
        *[
            (
                    "add:0[3],z",
                    {"add:0": np.array([4, 5, 6], dtype=np.float32), "z": np.array([1, 2, 3], dtype=np.float32)},
                    np.array([4, 10, 18], dtype=np.float32),
                    np.float32,
                    None
            ),
            (
                    "add:0{i32}[3],z{i32}",
                    {"add:0": np.array([4, 5, 6], dtype=np.int32), "z": np.array([1, 2, 3], dtype=np.int32)},
                    np.array([4, 10, 18], dtype=np.int32),
                    np.int32,
                    None
            ),
        ],
    )
    def test_cutting_fp32(self, input_freezing_value, inputs, expected,
                          dtype=None, freeze_placeholder_with_value=None, input_shape=None, only_conversion=False):
        self.basic("model_three_inputs.pb", input_freezing_value, inputs, dtype, expected,
                   freeze_placeholder_with_value,
                   input_shape, only_conversion)