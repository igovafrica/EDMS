from django import forms
from django.core.exceptions import ValidationError
from django.forms.formsets import formset_factory
from django.utils.text import format_lazy
from django.utils.translation import ugettext_lazy as _

from mayan.apps.templating.fields import TemplateField

from .classes import MetadataLookup
from .models import DocumentTypeMetadataType, MetadataType


class DocumentMetadataForm(forms.Form):
    metadata_type_id = forms.CharField(label=_('ID'), widget=forms.HiddenInput)
    metadata_type_name = forms.CharField(
        label=_('Name'), required=False,
        widget=forms.TextInput(attrs={'readonly': 'readonly'})
    )
    value = forms.CharField(
        label=_('Value'), required=False, widget=forms.TextInput(
            attrs={'class': 'metadata-value'}
        )
    )
    update = forms.BooleanField(
        initial=True, label=_('Update'), required=False
    )

    class Media:
        js = ('metadata/js/metadata_form.js',)

    def __init__(self, *args, **kwargs):
        super(DocumentMetadataForm, self).__init__(*args, **kwargs)

        # Set form fields initial values
        if 'initial' in kwargs:
            self.metadata_type = kwargs['initial']['metadata_type']
            self.document_type = kwargs['initial']['document_type']
            required_string = ''

            required = self.metadata_type.get_required_for(
                document_type=self.document_type
            )

            if required:
                self.fields['value'].required = True
                required_string = ' (%s)' % _('Required')
            else:
                self.fields['value'].required = False
                self.fields['update'].initial = False

            self.fields['metadata_type_name'].initial = '%s%s' % (
                (
                    self.metadata_type.label if self.metadata_type.label else self.metadata_type.name
                ),
                required_string
            )
            self.fields['metadata_type_id'].initial = self.metadata_type.pk

            if self.metadata_type.lookup:
                try:
                    self.fields['value'] = forms.ChoiceField(
                        label=self.fields['value'].label
                    )
                    choices = self.metadata_type.get_lookup_values()
                    choices = list(zip(choices, choices))
                    if not required:
                        choices.insert(0, ('', '------'))
                    self.fields['value'].choices = choices
                    self.fields['value'].required = required
                    self.fields['value'].widget.attrs.update(
                        {'class': 'metadata-value'}
                    )
                except Exception as exception:
                    self.fields['value'].initial = _(
                        'Lookup value error: %s'
                    ) % exception
                    self.fields['value'].widget = forms.TextInput(
                        attrs={'readonly': 'readonly'}
                    )

            if self.metadata_type.default:
                try:
                    self.fields[
                        'value'
                    ].initial = self.metadata_type.get_default_value()
                except Exception as exception:
                    self.fields['value'].initial = _(
                        'Default value error: %s'
                    ) % exception
                    self.fields['value'].widget = forms.TextInput(
                        attrs={'readonly': 'readonly'}
                    )

    def clean(self):
        metadata_type = getattr(self, 'metadata_type', None)

        if metadata_type:
            required = self.metadata_type.get_required_for(
                document_type=self.document_type
            )

            # Enforce required only if the metadata has no previous value.
            if required and not self.cleaned_data['value'] and not self.cleaned_data.get('update'):
                raise ValidationError(
                    _(
                        '"%s" is required for this document type.'
                    ) % self.metadata_type.label
                )

        if self.cleaned_data.get('update') and hasattr(self, 'metadata_type'):
            self.cleaned_data['value'] = self.metadata_type.validate_value(
                document_type=self.document_type,
                value=self.cleaned_data.get('value')
            )

        return self.cleaned_data


DocumentMetadataFormSet = formset_factory(form=DocumentMetadataForm, extra=0)


class DocumentMetadataAddForm(forms.Form):
    metadata_type = forms.ModelMultipleChoiceField(
        help_text=_('Metadata types to be added to the selected documents.'),
        label=_('Metadata type'), queryset=MetadataType.objects.all(),
        widget=forms.SelectMultiple(
            attrs={'class': 'select2'},
        )
    )

    def __init__(self, *args, **kwargs):
        document_type = kwargs.pop('document_type', None)

        if document_type:
            queryset = kwargs.pop(
                'queryset', MetadataType.objects.get_for_document_type(
                    document_type=document_type
                )
            )
        else:
            queryset = MetadataType.objects.none()

        super(DocumentMetadataAddForm, self).__init__(*args, **kwargs)

        self.fields['metadata_type'].queryset = queryset


class DocumentMetadataRemoveForm(DocumentMetadataForm):
    update = forms.BooleanField(
        initial=False, label=_('Remove'), required=False
    )

    def __init__(self, *args, **kwargs):
        super(DocumentMetadataRemoveForm, self).__init__(*args, **kwargs)
        self.fields.pop('value')

    def clean(self):
        return super(forms.Form, self).clean()


DocumentMetadataRemoveFormSet = formset_factory(
    form=DocumentMetadataRemoveForm, extra=0
)


class MetadataTypeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(MetadataTypeForm, self).__init__(*args, **kwargs)
        self.fields['default'] = TemplateField(
            initial_help_text=self.fields['default'].help_text, required=False
        )
        self.fields['lookup'] = TemplateField(
            initial_help_text=format_lazy(
                '{}{}{}',
                self.fields['lookup'].help_text,
                _(' Available template context variables: '),
                MetadataLookup.get_as_help_text()
            ), required=False
        )

    class Meta:
        fields = ('name', 'label', 'default', 'lookup', 'validation', 'parser')
        model = MetadataType


class DocumentTypeMetadataTypeRelationshipForm(forms.Form):
    RELATIONSHIP_TYPE_NONE = 'none'
    RELATIONSHIP_TYPE_OPTIONAL = 'optional'
    RELATIONSHIP_TYPE_REQUIRED = 'required'
    RELATIONSHIP_CHOICES = (
        (RELATIONSHIP_TYPE_NONE, _('None')),
        (RELATIONSHIP_TYPE_OPTIONAL, _('Optional')),
        (RELATIONSHIP_TYPE_REQUIRED, _('Required')),
    )

    label = forms.CharField(
        label=_('Label'), required=False,
        widget=forms.TextInput(attrs={'readonly': 'readonly'})
    )
    relationship_type = forms.ChoiceField(
        label=_('Relationship'),
        widget=forms.RadioSelect(), choices=RELATIONSHIP_CHOICES
    )

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop('_user')
        super(DocumentTypeMetadataTypeRelationshipForm, self).__init__(
            *args, **kwargs
        )

        if 'main_model' in self.initial:
            if self.initial['main_model'] == 'metadata_type':
                self.fields['label'].initial = self.initial['document_type'].label
            else:
                self.fields['label'].initial = self.initial['metadata_type'].label

            self.initial_relationship_type = self.get_relationship_type()
            self.fields['relationship_type'].initial = self.initial_relationship_type

    def get_relationship(self):
        return self.initial['document_type'].metadata.filter(
            metadata_type=self.initial['metadata_type']
        )

    def get_relationship_choices(self):
        return self.initial['document_type'].metadata.filter(
            metadata_type=self.initial['metadata_type']
        )

    def get_relationship_type(self):
        relationship = self.get_relationship()

        if relationship.exists():
            if relationship.get().required:
                return self.RELATIONSHIP_TYPE_REQUIRED
            else:
                return self.RELATIONSHIP_TYPE_OPTIONAL
        else:
            return self.RELATIONSHIP_TYPE_NONE

    def save(self):
        relationship = self.get_relationship()

        if self.cleaned_data['relationship_type'] != self.initial_relationship_type:
            getattr(
                self, 'save_relationship_{}'.format(
                    self.cleaned_data['relationship_type']
                )
            )(relationship=relationship)

    def save_relationship_none(self, relationship):
        relationship.get().delete(_user=self._user)

    def save_relationship_optional(self, relationship):
        if relationship.exists():
            instance = relationship.get()
            instance.required = False
            instance.save(_user=self._user)
        else:
            relationship = DocumentTypeMetadataType(
                document_type=self.initial['document_type'],
                metadata_type=self.initial['metadata_type'],
            )
            relationship.save(_user=self._user)

    def save_relationship_required(self, relationship):
        if relationship.exists():
            instance = relationship.get()
            instance.required = True
            instance.save(_user=self._user)
        else:
            relationship = DocumentTypeMetadataType(
                document_type=self.initial['document_type'],
                metadata_type=self.initial['metadata_type'],
                required=True,
            )
            relationship.save(_user=self._user)


DocumentTypeMetadataTypeRelationshipFormSetBase = formset_factory(
    form=DocumentTypeMetadataTypeRelationshipForm, extra=0
)


class DocumentTypeMetadataTypeRelationshipFormSet(DocumentTypeMetadataTypeRelationshipFormSetBase):
    def __init__(self, *args, **kwargs):
        _user = kwargs.pop('_user')
        super(DocumentTypeMetadataTypeRelationshipFormSet, self).__init__(*args, **kwargs)
        self.form_kwargs.update({'_user': _user})
