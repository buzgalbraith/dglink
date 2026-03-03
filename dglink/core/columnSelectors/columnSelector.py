"""
Base class for column selectors 
"""
import pandas


from abc import ABC, abstractmethod
from ...core.tabularDataset import tabularDataset

class columnSelector(ABC):
    name:str = NotImplemented

    @abstractmethod
    def execute(self, table:tabularDataset, verbose:bool = False):
        """Run the column selector
        
        Parameters:
            dataframe : pandas.Dataframe
                Data frame to select columns for 
            original_columns : List
                A list of all columns in the original data frame
        Returns 
            Data frame with selected columns 
            List with columns that were selected
        """
    
    @abstractmethod
    def check_column(self, table:tabularDataset, col:str, verbose:bool = False)->bool:
        """Check if a single column contains entities"""