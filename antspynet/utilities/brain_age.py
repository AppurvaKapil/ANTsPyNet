import os

import statistics
import numpy as np
import keras

import ants

def brain_age(t1,
              do_preprocessing=True,
              output_directory=None,
              verbose=False):

    """
    Brain Age

    Estimate BrainAge from a T1-weighted MR image using the DeepBrainNet
    architecture and weights described here:

    https://github.com/vishnubashyam/DeepBrainNet

    and described in the following article:

    https://academic.oup.com/brain/article-abstract/doi/10.1093/brain/awaa160/5863667?redirectedFrom=fulltext

    Preprocessing on the training data consisted of:
       * n4 bias correction,
       * brain extraction, and
       * affine registration to MNI.
    The input T1 should undergo the same steps.  If the input T1 is the raw
    T1, these steps can be performed by the internal preprocessing, i.e. set
    do_preprocessing = True

    Arguments
    ---------
    t1 : ANTsImage
        raw or preprocessed 3-D T1-weighted brain image.

    do_preprocessing : boolean
        See description above.

    output_directory : string
        Destination directory for storing the downloaded template and model weights.
        Since these can be resused, if is None, these data will be downloaded to a
        tempfile.

    verbose : boolean
        Print progress to the screen.

    Returns
    -------
    List consisting of the segmentation image and probability images for
    each label.

    Example
    -------
    >>> image = ants.image_read("t1.nii.gz")
    >>> deep = brain_age(image)
    >>> print("Predicted age: ", deep['predicted_age'])

    """

    from ..utilities import preprocess_brain_image
    from ..utilities import get_pretrained_network

    if t1.dimension != 3:
        raise ValueError( "Image dimension must be 3." )

    ################################
    #
    # Preprocess images
    #
    ################################

    t1_preprocessed = t1
    if do_preprocessing == True:
        t1_preprocessing = preprocess_brain_image(t1,
            truncate_intensity=(0.01, 0.99),
            do_brain_extraction=True,
            template="croppedMni152",
            template_transform_type="AffineFast",
            do_bias_correction=True,
            do_denoising=False,
            output_directory=output_directory,
            verbose=verbose)
        t1_preprocessed = t1_preprocessing["preprocessed_image"] * t1_preprocessing['brain_mask']

    t1_preprocessed = (t1_preprocessed - t1_preprocessed.min()) / (t1_preprocessed.max() - t1_preprocessed.min())

    ################################
    #
    # Load model and weights
    #
    ################################

    model_weights_file_name = None
    if output_directory is not None:
        model_weights_file_name = output_directory + "/DeepBrainNetModel.h5"
        if not os.path.exists(model_weights_file_name):
            if verbose == True:
                print("Brain age (DeepBrainNet):  downloading model weights.")
            model_weights_file_name = get_pretrained_network("brainAgeDeepBrainNet", model_weights_file_name)
    else:
        model_weights_file_name = get_pretrained_network("brainAgeDeepBrainNet")

    model = keras.models.load_model(model_weights_file_name)

    # The paper only specifies that 80 slices are used for prediction.  I just picked
    # a reasonable range spanning the center of the brain

    which_slices = list(range(45, 125))

    batchX = np.zeros((len(which_slices), *t1_preprocessed.shape[0:2], 3))

    for i in range(len(which_slices)):

        # The model requires a three-channel input.  The paper doesn't specify but I'm
        # guessing that the previous and next slice are included.

        batchX[i,:,:,0] = (ants.slice_image(t1_preprocessed, axis=2, idx=which_slices[i] - 1)).numpy()
        batchX[i,:,:,1] = (ants.slice_image(t1_preprocessed, axis=2, idx=which_slices[i]    )).numpy()
        batchX[i,:,:,2] = (ants.slice_image(t1_preprocessed, axis=2, idx=which_slices[i] + 1)).numpy()


    if verbose == True:
        print("Brain age (DeepBrainNet):  predicting brain age per slice.")

    brain_age_per_slice = model.predict(batchX, verbose=verbose)

    predicted_age = statistics.median(brain_age_per_slice)[0]

    return_dict = {'predicted_age' : predicted_age,
                   'brain_age_per_slice' : brain_age_per_slice}
    return(return_dict)