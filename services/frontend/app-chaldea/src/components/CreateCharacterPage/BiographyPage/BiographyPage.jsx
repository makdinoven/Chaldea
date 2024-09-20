import { useState, useRef } from 'react';

import FormButton from '../../CommonComponents/BlueGradientButton/BlueGradientButton';
import Input from '../../CommonComponents/Input/Input';
import Select from '../../CommonComponents/Select/Select';
import Textarea from '../../CommonComponents/Textarea/Textarea';

import styles from './BiographyPage.module.css';

export default function BiographyPage({
  selectedRaceId,
  selectedSubraceId,
  selectedClassId,
}) {
  const [formValues, setFormValues] = useState({
    name: '',
    age: '',
    height: '',
    weight: '',
    origin: '',
    sex: '',
    biography: '',
    personality: '',
    appearance: '',
  });

  const fileInputRef = useRef(null);

  const handlePhotoInputClick = () => {
    fileInputRef.current.click();
  };

  const handleInputChange = (e) => {
    const { id, value } = e.target;
    setFormValues((prevValues) => ({
      ...prevValues,
      [id]: value,
    }));
  };

  const handleSelectChange = (e) => {
    const { value } = e.target;
    setFormValues((prevValues) => ({
      ...prevValues,
      sex: value,
    }));
  };

  const handleTextareaChange = (e) => {
    const { id, value } = e.target;
    setFormValues((prevValues) => ({
      ...prevValues,
      [id]: value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    console.log('Selected Race:', selectedRaceId);
    console.log('Selected Subrace:', selectedSubraceId);
    console.log('Selected Class:', selectedClassId);
    console.log('Form:', formValues);
  };

  const inputsData = [
    { id: 'name', isRequired: true, text: 'Имя персонажа*', maxLength: 20 },
    { id: 'age', text: 'Возраст', type: 'number' },
    { id: 'height', text: 'Рост', type: 'number' },
    { id: 'weight', text: 'Вес', type: 'number' },
    { id: 'origin', text: 'Происхождение', maxLength: 20 },
  ];

  const selectOptions = [
    { name: 'Выберите пол', value: '', isDisabled: true },
    { name: 'Мужской', value: 'Мужской' },
    { name: 'Женский', value: 'Женский' },
  ];

  const textareasData = [
    { id: 'biography', text: 'Биография*', isRequired: true, link: '/rules' },
    { id: 'personality', text: 'Личность*', isRequired: true, link: '/rules' },
    { id: 'appearance', text: 'Внешность*', isRequired: true, link: '/rules' },
  ];

  return (
    <form className={styles.form} action=''>
      <div className={styles.form_inner}>
        <div className={styles.textareas_container}>
          {textareasData.map((data, index) => (
            <Textarea
              key={index}
              id={data.id}
              text={data.text}
              link={data.link}
              isRequired={data.isRequired}
              value={formValues[data.id]} // Привязка значения
              onChange={handleTextareaChange} // Обработчик изменения
            />
          ))}
        </div>
        <div className={styles.inputs_container}>
          <div className={styles.inputs_wrapper}>
            {inputsData.map((data, index) => (
              <Input
                isRequired={data.isRequired}
                key={index}
                id={data.id}
                type={data.type}
                maxLength={data.maxLength}
                text={data.text}
                value={formValues[data.id]} // Привязка значения
                onChange={handleInputChange} // Обработчик изменения
              />
            ))}
            <Select options={selectOptions} onChange={handleSelectChange} />
          </div>
          <div
            className={styles.custom_file_upload}
            onClick={handlePhotoInputClick}
          >
            <label htmlFor='fileInput'>Сменить аватар</label>
            <input
              style={{ display: 'none' }}
              ref={fileInputRef}
              type='file'
              id='fileInput'
              accept='image/*'
            />
          </div>
        </div>
      </div>
      <div className={styles.button_container}>
        <FormButton text='Отправить анкету' onClick={handleSubmit} />
      </div>
    </form>
  );
}
