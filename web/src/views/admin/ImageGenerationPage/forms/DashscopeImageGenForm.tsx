"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import * as Yup from "yup";
import { Button, InputTypeIn, PasswordInputTypeIn } from "@opal/components";
import { SvgRefreshCw, SvgSimpleLoader } from "@opal/icons";
import { toast } from "@opal/layouts";
import { FormikField } from "@/refresh-components/form/FormikField";
import { FormField } from "@/refresh-components/form/FormField";
import InputComboBox from "@/refresh-components/inputs/InputComboBox";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { ImageGenFormWrapper } from "@/views/admin/ImageGenerationPage/forms/ImageGenFormWrapper";
import {
  ImageGenFormBaseProps,
  ImageGenFormChildProps,
  ImageGenSubmitPayload,
} from "@/views/admin/ImageGenerationPage/forms/types";
import {
  ImageProvider,
} from "@/views/admin/ImageGenerationPage/constants";
import {
  DashscopeImageModel,
  ImageGenerationConfigView,
  ImageGenerationCredentials,
  fetchDashscopeImageModels,
} from "@/views/admin/ImageGenerationPage/svc";
import {
  DASHSCOPE_CUSTOM_REGION,
  DASHSCOPE_IMAGE_SEED_MODELS,
  DASHSCOPE_REGIONS,
  composeDashscopeBase,
  parseDashscopeBase,
} from "@/lib/languageModels/dashscope";

const DASHSCOPE_PROVIDER_NAME = "dashscope";
const DASHSCOPE_RECOMMENDED_IMAGE_MODEL = "qwen-image-3.0";
const DEFAULT_REGION = "cn-beijing";

// Kept in sync with the backend's supported qwen-image parameters.
const QWEN_IMAGE_MODEL_PARAMS = {
  supports_reference_images: true,
  max_reference_images: 3,
  default_size: "1024x1024",
  size_range: "512x512-2048x2048",
  max_images_per_request: 6,
  watermark: false,
  prompt_extend: true,
};

const SEED_MODELS: DashscopeImageModel[] = DASHSCOPE_IMAGE_SEED_MODELS.map(
  (model) => ({
    name: model.name,
    display_name: model.label,
    is_recommended_default: model.name === DASHSCOPE_RECOMMENDED_IMAGE_MODEL,
    ...QWEN_IMAGE_MODEL_PARAMS,
  })
);

// DashScope form values
interface DashscopeImageGenFormValues {
  api_key: string;
  workspace_id: string;
  region: string;
  custom_api_base: string;
  model_name: string;
}

function getInitialValues(
  imageProvider: ImageProvider,
  existingConfig?: ImageGenerationConfigView
): DashscopeImageGenFormValues {
  return {
    api_key: "",
    workspace_id: "",
    region: DEFAULT_REGION,
    custom_api_base: "",
    model_name: existingConfig?.model_name ?? imageProvider.model_name,
  };
}

function getInitialValuesFromCredentials(
  credentials: ImageGenerationCredentials,
  _imageProvider: ImageProvider
): Partial<DashscopeImageGenFormValues> {
  const parsedBase = parseDashscopeBase(credentials.api_base);
  return {
    workspace_id: parsedBase.workspaceId,
    region: parsedBase.region,
    custom_api_base: parsedBase.customBase,
  };
}

/** Each model maps to its own config row so models stay separately managed. */
function imageProviderIdForModel(
  imageProvider: ImageProvider,
  modelName: string
): string {
  return modelName === imageProvider.model_name
    ? imageProvider.image_provider_id
    : `dashscope_${modelName}`;
}

function transformValues(
  values: DashscopeImageGenFormValues,
  imageProvider: ImageProvider
): ImageGenSubmitPayload {
  return {
    modelName: values.model_name,
    imageProviderId: imageProviderIdForModel(imageProvider, values.model_name),
    provider: DASHSCOPE_PROVIDER_NAME,
    apiKey: values.api_key,
    apiBase: composeDashscopeBase(
      values.workspace_id,
      values.region,
      values.custom_api_base
    ),
  };
}

interface DashscopeImageGenFieldsProps
  extends ImageGenFormChildProps<DashscopeImageGenFormValues> {
  existingConfig?: ImageGenerationConfigView;
}

function DashscopeImageGenFields(props: DashscopeImageGenFieldsProps) {
  const t = useTranslations("admin.imageGeneration");
  const {
    apiStatus,
    showApiMessage,
    errorMessage,
    disabled,
    isLoadingCredentials,
    apiKeyOptions,
    resetApiState,
    imageProvider,
    formikProps,
    existingConfig,
  } = props;
  const { values, setFieldValue } = formikProps;

  const isCustomRegion = values.region === DASHSCOPE_CUSTOM_REGION;
  const isBaseReady = isCustomRegion
    ? values.custom_api_base.trim() !== ""
    : values.workspace_id.trim() !== "";
  // On edit the key is masked; the backend resolves the stored one via
  // provider_id as long as the endpoint is unchanged.
  const canFetchModels =
    isBaseReady && (!!values.api_key || !!existingConfig?.llm_provider_id);
  const composedApiBase = composeDashscopeBase(
    values.workspace_id,
    values.region,
    values.custom_api_base
  );

  const [models, setModels] = useState<DashscopeImageModel[]>(SEED_MODELS);
  const [isFetchingModels, setIsFetchingModels] = useState(false);

  const fetchModels = async (isAutoFetch: boolean) => {
    setIsFetchingModels(true);
    try {
      const fetched = await fetchDashscopeImageModels(
        values.api_key || undefined,
        composedApiBase,
        existingConfig?.llm_provider_id
      );
      if (fetched.length > 0) {
        setModels(fetched);
      }
    } catch (error) {
      // Auto-fetch stays silent so the seed list still works; a manual
      // refresh surfaces the problem.
      if (!isAutoFetch) {
        toast.error(
          error instanceof Error
            ? error.message
            : t("dashscope.models.fetchError")
        );
      }
    } finally {
      setIsFetchingModels(false);
    }
  };

  // Fetch once when the workspace endpoint becomes ready, so the picker
  // matches what the Bailian workspace actually offers.
  const autoFetchedRef = useRef(false);
  useEffect(() => {
    if (autoFetchedRef.current || !canFetchModels || isFetchingModels) return;
    autoFetchedRef.current = true;
    void fetchModels(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canFetchModels]);

  const selectedModel = models.find((m) => m.name === values.model_name);

  return (
    <>
      {/* Region select */}
      <FormikField<string>
        name="region"
        render={(field, helper, _meta, state) => (
          <FormField name="region" state={state} className="w-full">
            <FormField.Label>{t("dashscope.region.label")}</FormField.Label>
            <FormField.Control>
              <InputSelect
                value={field.value}
                onValueChange={(value) => helper.setValue(value)}
                disabled={disabled}
              >
                <InputSelect.Trigger />
                <InputSelect.Content>
                  {DASHSCOPE_REGIONS.map((region) => (
                    <InputSelect.Item
                      key={region.code}
                      value={region.code}
                      description={region.code}
                    >
                      {region.label}
                    </InputSelect.Item>
                  ))}
                  <InputSelect.Separator />
                  <InputSelect.Item
                    value={DASHSCOPE_CUSTOM_REGION}
                    description={t("dashscope.region.custom.description")}
                  >
                    {t("dashscope.region.custom.label")}
                  </InputSelect.Item>
                </InputSelect.Content>
              </InputSelect>
            </FormField.Control>
            <FormField.Message
              messages={{ idle: t("dashscope.region.idle") }}
            />
          </FormField>
        )}
      />

      {/* Workspace ID */}
      {!isCustomRegion && (
        <FormikField<string>
          name="workspace_id"
          render={(field, helper, meta, state) => (
            <FormField
              name="workspace_id"
              state={state}
              className="w-full"
            >
              <FormField.Label>
                {t("dashscope.workspaceId.label")}
              </FormField.Label>
              <FormField.Control>
                <InputTypeIn
                  value={field.value}
                  onChange={(e) => helper.setValue(e.target.value)}
                  onBlur={field.onBlur}
                  placeholder="your-workspace-id"
                  variant={disabled ? "disabled" : undefined}
                />
              </FormField.Control>
              <FormField.Message
                messages={{
                  idle: t("dashscope.workspaceId.idle"),
                  error: meta.error,
                }}
              />
            </FormField>
          )}
        />
      )}

      {/* Custom endpoint (legacy domains etc.) */}
      {isCustomRegion && (
        <FormikField<string>
          name="custom_api_base"
          render={(field, helper, meta, state) => (
            <FormField
              name="custom_api_base"
              state={state}
              className="w-full"
            >
              <FormField.Label>
                {t("dashscope.customBase.label")}
              </FormField.Label>
              <FormField.Control>
                <InputTypeIn
                  value={field.value}
                  onChange={(e) => helper.setValue(e.target.value)}
                  onBlur={field.onBlur}
                  placeholder="https://dashscope.aliyuncs.com"
                  variant={disabled ? "disabled" : undefined}
                />
              </FormField.Control>
              <FormField.Message
                messages={{
                  idle: t("dashscope.customBase.idle"),
                  error: meta.error,
                }}
              />
            </FormField>
          )}
        />
      )}

      {/* API key */}
      <FormikField<string>
        name="api_key"
        render={(field, helper, meta, state) => (
          <FormField
            name="api_key"
            state={apiStatus === "error" ? "error" : state}
            className="w-full"
          >
            <FormField.Label>{t("form.apiKey.label")}</FormField.Label>
            <FormField.Control>
              {apiKeyOptions.length > 0 ? (
                <InputComboBox
                  value={field.value}
                  onChange={(e) => {
                    helper.setValue(e.target.value);
                    resetApiState();
                  }}
                  onValueChange={(value) => {
                    helper.setValue(value);
                    resetApiState();
                  }}
                  onBlur={field.onBlur}
                  options={apiKeyOptions}
                  placeholder={
                    isLoadingCredentials
                      ? t("form.loading.placeholder")
                      : t("form.apiKey.comboPlaceholder")
                  }
                  disabled={disabled}
                  isError={apiStatus === "error"}
                />
              ) : (
                <PasswordInputTypeIn
                  {...field}
                  onChange={(e) => {
                    field.onChange(e);
                    resetApiState();
                  }}
                  placeholder={
                    isLoadingCredentials
                      ? t("form.loading.placeholder")
                      : t("form.apiKey.placeholder")
                  }
                  disabled={disabled}
                  error={apiStatus === "error"}
                />
              )}
            </FormField.Control>
            {showApiMessage ? (
              <FormField.APIMessage
                state={apiStatus}
                messages={{
                  loading: t("form.apiKeyTest.loading", {
                    title: imageProvider.title,
                  }),
                  success: t("form.apiKeyTest.success"),
                  error: errorMessage || t("form.apiKeyTest.error"),
                }}
              />
            ) : (
              <FormField.Message
                messages={{
                  idle: t("dashscope.apiKey.idle"),
                  error: meta.error,
                }}
              />
            )}
          </FormField>
        )}
      />

      {/* Model select with live workspace fetch */}
      <FormikField<string>
        name="model_name"
        render={(field, helper, meta, state) => (
          <FormField name="model_name" state={state} className="w-full">
            <FormField.Label>{t("dashscope.models.label")}</FormField.Label>
            <FormField.Control>
              <div className="flex w-full items-center gap-2">
                <div className="flex min-w-0 flex-1">
                  <InputSelect
                    value={field.value}
                    onValueChange={(value) => helper.setValue(value)}
                    disabled={disabled}
                  >
                    <InputSelect.Trigger />
                    <InputSelect.Content>
                      {models.map((model) => (
                        <InputSelect.Item
                          key={model.name}
                          value={model.name}
                          description={
                            model.is_recommended_default
                              ? t("dashscope.models.recommended.description")
                              : undefined
                          }
                        >
                          {model.display_name}
                        </InputSelect.Item>
                      ))}
                    </InputSelect.Content>
                  </InputSelect>
                </div>
                <Button
                  prominence="tertiary"
                  icon={
                    isFetchingModels ? SvgSimpleLoader : SvgRefreshCw
                  }
                  onClick={() => void fetchModels(false)}
                  disabled={disabled || isFetchingModels || !canFetchModels}
                  tooltip={
                    canFetchModels
                      ? t("dashscope.models.refresh.tooltip")
                      : t("dashscope.models.refresh.disabledTooltip")
                  }
                  aria-label={t("dashscope.models.refresh.ariaLabel")}
                />
              </div>
            </FormField.Control>
            <FormField.Message
              messages={{
                idle:
                  selectedModel != null
                    ? t("dashscope.models.params", {
                        size: selectedModel.default_size,
                        sizeRange: selectedModel.size_range,
                        maxImages: selectedModel.max_images_per_request,
                        referenceImages: selectedModel.max_reference_images,
                      })
                    : t("dashscope.models.idle"),
                error: meta.error,
              }}
            />
          </FormField>
        )}
      />
    </>
  );
}

export function DashscopeImageGenForm(props: ImageGenFormBaseProps) {
  const t = useTranslations("admin.imageGeneration");
  const { imageProvider, existingConfig } = props;

  const validationSchema = useMemo(
    () =>
      Yup.object().shape({
        api_key: Yup.string().required(t("form.apiKey.required")),
        region: Yup.string().required(t("dashscope.region.required")),
        workspace_id: Yup.string().when("region", {
          is: (region: string) => region !== DASHSCOPE_CUSTOM_REGION,
          then: (schema) =>
            schema.required(t("dashscope.workspaceId.required")),
          otherwise: (schema) => schema.notRequired(),
        }),
        custom_api_base: Yup.string().when("region", {
          is: DASHSCOPE_CUSTOM_REGION,
          then: (schema) =>
            schema.required(t("dashscope.customBase.required")),
          otherwise: (schema) => schema.notRequired(),
        }),
        model_name: Yup.string().required(t("dashscope.models.required")),
      }),
    [t]
  );

  return (
    <ImageGenFormWrapper<DashscopeImageGenFormValues>
      {...props}
      title={
        existingConfig
          ? t("form.editHeader.title", { title: imageProvider.title })
          : t("form.connectHeader.title", { title: imageProvider.title })
      }
      description={t(imageProvider.descriptionKey)}
      initialValues={getInitialValues(imageProvider, existingConfig)}
      validationSchema={validationSchema}
      getInitialValuesFromCredentials={getInitialValuesFromCredentials}
      transformValues={(values) => transformValues(values, imageProvider)}
    >
      {(childProps) => (
        <DashscopeImageGenFields {...childProps} existingConfig={existingConfig} />
      )}
    </ImageGenFormWrapper>
  );
}
