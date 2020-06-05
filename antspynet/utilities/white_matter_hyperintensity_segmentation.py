import os
import numpy as np
import keras

import ants

def sysu_media_wmh_segmentation(flair, 
                                t1=None, 
                                brain_mask=None, 
                                do_preprocessing=True, 
                                use_ensemble=True, 
                                output_directory=None, 
                                verbose=False):

    """
    Perform WMH segmentation using the winning submission in the MICCAI
    2017 challenge by the sysu_media team using FLAIR or T1/FLAIR.  The 
    MICCAI challenge is discussed in 
    
    https://pubmed.ncbi.nlm.nih.gov/30908194/
   
    with the sysu_media's team entry is discussed in 
   
     https://pubmed.ncbi.nlm.nih.gov/30125711/
   
    with the original implementation available here:
   
    https://github.com/hongweilibran/wmh_ibbmTum

    Arguments
    ---------
    flair : ANTsImage
        input 3-D FLAIR brain image.

    t1 : ANTsImage
        input 3-D T1 brain image.

    brain_mask : ANTsImage
        input 3-D brain mask image.  If not specified, getMask()
        is used to estimate a mask which is not recommended.
    
    do_preprocessing : boolean
        perform n4 bias correction?

    use_ensemble : boolean
        check whether to use all 3 sets of weights.  

    output_directory : string
        Destination directory for storing the downloaded template and model weights.  
        Since these can be resused, if is None, these data will be downloaded to a 
        tempfile.

    verbose : boolean
        Print progress to the screen.    

    Returns
    -------
    WMH segmentation probability image

    Example
    -------
    >>> image = ants.image_read("flair.nii.gz")
    >>> probability_mask = sysu_media_wmh_segmentation(image)
    """

    from ..architectures import create_sysu_media_unet_model_2d
    from ..utilities import get_pretrained_network
    from ..utilities import preprocess_brain_image
    from ..utilities import crop_image_center

    def pad_or_crop_image_to_size(image, size):
        image_size = np.array(image.shape)
        delta = image_size - np.array(size)

        if np.any(delta < 0):
            pad_size = abs(delta.min())
            pad_shape = image_size + pad_size
            image = ants.pad_image(image, shape=pad_shape)

        cropped_image = crop_image_center(image, size)
        return(cropped_image)

    if flair.dimension != 3:
        raise ValueError( "Image dimension must be 3." )  

    ################################
    #
    # Preprocess images
    #
    ################################  

    flair_preprocessed = flair
    if do_preprocessing == True:
        flair_preprocessing = preprocess_brain_image(flair,
            truncate_intensity=(0.01, 0.99),
            do_brain_extraction=False,
            do_bias_correction=True,
            do_denoising=False,
            output_directory=output_directory,
            verbose=verbose)
        flair_preprocessed = flair_preprocessing["preprocessed_image"]    

    number_of_channels = 1
    if t1 is not None:
        t1_preprocessed = t1
        if do_preprocessing == True:
            t1_preprocessing = preprocess_brain_image(t1,
                truncate_intensity=(0.01, 0.99),
                do_brain_extraction=False,
                do_bias_correction=True,
                do_denoising=False,
                output_directory=output_directory,
                verbose=verbose)
            t1_preprocessed = t1_preprocessing["preprocessed_image"]    
        number_of_channels = 2

    ################################
    #
    # Estimate mask (if not specified)
    #
    ################################  

    if brain_mask is None:
        if verbose == True:
            print("Estimating brain mask.")
        if t1 is not None:
            brain_mask = ants.get_mask(t1, cleanup=2)
        else:    
            brain_mask = ants.get_mask(flair, cleanup=2)

    reference_image = ants.make_image((200, 200, 200), 
                                      voxval=1,
                                      spacing=(1, 1, 1),
                                      origin=(0, 0, 0),
                                      direction=np.identity(3))

    center_of_mass_reference = ants.get_center_of_mass(reference_image)
    center_of_mass_image = ants.get_center_of_mass(brain_mask)
    translation = np.asarray(center_of_mass_image) - np.asarray(center_of_mass_reference)
    xfrm = ants.create_ants_transform(transform_type="Euler3DTransform",
        center=np.asarray(center_of_mass_reference), translation=translation)
    flair_preprocessed_warped = ants.apply_ants_transform_to_image(xfrm, flair_preprocessed, reference_image)
    brain_mask_warped = ants.threshold_image( 
        ants.apply_ants_transform_to_image(xfrm, brain_mask, reference_image), 0.5, 1.1, 1, 0 )

    if t1 is not None:
        t1_preprocessed_warped = ants.apply_ants_transform_to_image(xfrm, t1_preprocessed, reference_image)

    ################################
    #
    # Gaussian normalize intensity based on brain mask
    #
    ################################  

    mean_flair = flair_preprocessed_warped[brain_mask_warped > 0].mean()
    std_flair = flair_preprocessed_warped[brain_mask_warped > 0].std()
    flair_preprocessed_warped = (flair_preprocessed_warped - mean_flair) / std_flair

    if number_of_channels == 2:
        mean_t1 = t1_preprocessed_warped[brain_mask_warped > 0].mean()
        std_t1 = t1_preprocessed_warped[brain_mask_warped > 0].std()
        t1_preprocessed_warped = (t1_preprocessed_warped - mean_t1) / std_t1

    ################################
    #
    # Build models and load weights
    #
    ################################  

    number_of_models = 1
    if use_ensemble == True:
        number_of_models = 3

    unet_models = list()
    for i in range(number_of_models):
        weights_file_name = None
        if number_of_channels == 1:
            if output_directory is not None:
                weights_file_name = output_directory + "sysuMediaWmhFlairOnlyModel" + str(i) + ".h5"
                if not os.path.exists(weights_file_name):
                    if verbose == True:
                        print("White matter hyperintensity:  downloading model weights.")
                    weights_file_name = get_pretrained_network("sysuMediaWmhFlairOnlyModel" + str(i), weights_file_name)
            else:    
                weights_file_name = get_pretrained_network("sysuMediaWmhFlairOnlyModel" + str(i))
        else:
            if output_directory is not None:
                weights_file_name = output_directory + "sysuMediaWmhFlairT1Model" + str(i) + ".h5"
                if not os.path.exists(weights_file_name):
                    if verbose == True:
                        print("White matter hyperintensity:  downloading model weights.")
                    weights_file_name = get_pretrained_network("sysuMediaWmhFlairT1Model" + str(i), weights_file_name)
            else:    
                weights_file_name = get_pretrained_network("sysuMediaWmhFlairT1Model" + str(i))
        
        unet_models.append(create_sysu_media_unet_model_2d((200, 200, number_of_channels)))
        unet_models[i].load_weights(weights_file_name)

    ################################
    #
    # Extract slices
    #
    ################################  

    number_of_axial_slices = flair_preprocessed_warped.shape[2]

    if verbose == True:
        print("Extracting slices.")

    batchX = np.zeros((number_of_axial_slices, 200, 200, number_of_channels))
    for i in range(number_of_axial_slices):
        flair_slice = pad_or_crop_image_to_size(ants.slice_image(flair_preprocessed_warped, 2, i), (200, 200))
        batchX[i,:,:,0] = flair_slice.numpy()
        if number_of_channels == 2:
            t1_slice = pad_or_crop_image_to_size(ants.slice_image(t1_preprocessed_warped, 2, i), (200, 200))
            batchX[i,:,:,1] = t1_slice.numpy()

    ################################
    #
    # Do prediction and then restack into the image
    #
    ################################  

    if verbose == True:
        print("Prediction.")
  
    prediction = unet_models[0].predict(batchX, verbose=verbose)
    if number_of_models > 1:
       for i in range(1, number_of_models, 1):
           prediction += unet_models[i].predict(batchX, verbose=verbose)
    prediction /= number_of_models

    prediction_array = np.transpose(np.squeeze(prediction), (1, 2, 0))
    prediction_image = pad_or_crop_image_to_size(ants.from_numpy(prediction_array), flair_preprocessed_warped.shape)
    probability_image_warped = ants.copy_image_info(flair_preprocessed_warped, prediction_image)
    probability_image = ants.apply_ants_transform_to_image(ants.invert_ants_transform(xfrm), 
        probability_image_warped, flair)

    return( probability_image )