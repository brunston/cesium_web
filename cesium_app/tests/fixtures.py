'''Assortment of fixtures for use in test modules.'''

import uuid
import os
from os.path import join as pjoin
from contextlib import contextmanager
from cesium_app import models
from cesium import data_management, featurize
from cesium.features import CADENCE_FEATS, GENERAL_FEATS, LOMB_SCARGLE_FEATS
from cesium.tests import fixtures
from cesium_app.ext.sklearn_models import MODELS_TYPE_DICT
import shutil
import peewee
import datetime
import joblib
import pandas as pd

from .conftest import cfg


@contextmanager
def create_test_project():
    """Create and yield test project, then delete."""
    p = models.Project.add_by('test_proj', 'test_desc', 'testuser@gmail.com')
    p.save()
    try:
        yield p
    finally:
        p.delete_instance()


@contextmanager
def create_test_dataset(project, label_type='class'):
    """Create and yield test labeled dataset, then delete.

    Params
    ------
    project : `models.Project` instance
        The project under which to create test dataset.
    label_type : str, optional
        String indicating whether data labels are class names for
        classification ('class'), numerical values for regression ('regr'),
        or no labels (anything else).
        Defaults to 'class'.
    """
    if label_type == 'class':
        header = pjoin(os.path.dirname(__file__),
                       'data', 'asas_training_subset_classes.dat')
    elif label_type == 'regr':
        header = pjoin(os.path.dirname(__file__),
                       'data', 'asas_training_subset_targets.dat')
    else:
        header = None
    tarball = pjoin(os.path.dirname(__file__),
                    'data', 'asas_training_subset.tar.gz')
    header = shutil.copy2(header, cfg['paths:upload_folder']) if header else None
    tarball = shutil.copy2(tarball, cfg['paths:upload_folder'])
    ts_paths = data_management.parse_and_store_ts_data(
        tarball, cfg['paths:ts_data_folder'], header)
    d = models.Dataset.add(name='test_ds', project=project, file_uris=ts_paths)
    d.save()
    try:
        yield d
    finally:
        d.delete_instance()


@contextmanager
def create_test_featureset(project, label_type='class'):
    """Create and yield test labeled featureset, then delete.

    Parameters
    ----------
    project : `models.Project` instance
        The project under which to create test feature set.
    label_type : {'class', 'regr', 'none'}, optional
        String indicating whether data are labeled with class names ('class')
        for classification, numerical values for regression ('regr'), or
        unlabeled ('none'). Defaults to 'class'.

    """
    if label_type == 'class':
        labels = ['Mira', 'Classical_Cepheid']
    elif label_type == 'regr':
        labels = [2.2, 3.4, 4.4, 2.2, 3.1]
    else:
        labels = []
    features_to_use = (CADENCE_FEATS + GENERAL_FEATS + LOMB_SCARGLE_FEATS)
    fset_data, fset_labels = fixtures.sample_featureset(5, 1, features_to_use,
                                                        labels)
    fset_path = pjoin(cfg['paths:features_folder'],
                      '{}.npz'.format(str(uuid.uuid4())))
    featurize.save_featureset(fset_data, fset_path, labels=fset_labels)
    f, created = models.File.get_or_create(uri=fset_path)
    fset = models.Featureset.create(name='test_featureset', file=f,
                                    project=project,
                                    features_list=features_to_use,
                                    custom_features_script=None,
                                    finished=datetime.datetime.now())
    fset.save()
    try:
        yield fset
    finally:
        fset.delete_instance()


@contextmanager
def create_test_model(fset, model_type='RandomForestClassifier'):
    """Create and yield test model, then delete.

    Params
    ------
    fset : `models.Featureset` instance
        The (labeled) feature set from which to build the model.
    model_type : str, optional
        String indicating type of model to build. Defaults to
        'RandomForestClassifier'.

    """
    model_params = {
        "RandomForestClassifier": {
            "bootstrap": True, "criterion": "gini",
            "oob_score": False, "max_features": "auto",
            "n_estimators": 10, "random_state": 0},
        "RandomForestRegressor": {
            "bootstrap": True, "criterion": "mse",
            "oob_score": False, "max_features": "auto",
            "n_estimators": 10},
        "LinearSGDClassifier": {
            "loss": "hinge"},
        "LinearRegressor": {
            "fit_intercept": True}}
    fset_data, data = featurize.load_featureset(fset.file.uri)
    model = MODELS_TYPE_DICT[model_type](**model_params[model_type])
    model.fit(fset_data, data['labels'])
    model_path = pjoin(cfg['paths:models_folder'],
                       '{}.pkl'.format(str(uuid.uuid4())))
    joblib.dump(model, model_path)
    f, created = models.File.get_or_create(uri=model_path)
    model = models.Model.create(name='test_model',
                                file=f, featureset=fset, project=fset.project,
                                params=model_params[model_type], type=model_type,
                                finished=datetime.datetime.now())
    model.save()
    try:
        yield model
    finally:
        model.delete_instance()


@contextmanager
def create_test_prediction(dataset, model, featureset=None):
    """Create and yield test prediction, then delete.

    Params
    ------
    dataset : `models.Dataset` instance
        Dummy dataset used to create prediction instance.
    model : `models.Model` instance
        The model to use to create prediction.
    featureset : `models.Featureset` instance, optional
        The featureset on which prediction will be performed. If None,
        the featureset associated with `model` will be used. Defaults
        to None.

    """
    if featureset is None:
        featureset = model.featureset
    fset, data = featurize.load_featureset(featureset.file.uri)
    model_data = joblib.load(model.file.uri)
    if hasattr(model_data, 'best_estimator_'):
        model_data = model_data.best_estimator_
    preds = model_data.predict(fset)
    pred_probs = (pd.DataFrame(model_data.predict_proba(fset),
                               index=fset.index, columns=model_data.classes_)
                  if hasattr(model_data, 'predict_proba') else [])
    all_classes = model_data.classes_ if hasattr(model_data, 'classes_') else []
    pred_path = pjoin(cfg['paths:predictions_folder'],
                      '{}.npz'.format(str(uuid.uuid4())))
    featurize.save_featureset(fset, pred_path, labels=data['labels'],
                              preds=preds, pred_probs=pred_probs)
    f, created = models.File.get_or_create(uri=pred_path)
    pred = models.Prediction.create(file=f, dataset=dataset,
                                    project=dataset.project,
                                    model=model, finished=datetime.datetime.now())
    pred.save()
    try:
        yield pred
    finally:
        pred.delete_instance()
